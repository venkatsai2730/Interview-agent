# Report generation — scorecard, discovery-brief, audit-log, coaching-report
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


# ---------------------------------------------------------------------------
# In-memory report dataclasses (not ORM models)
# ---------------------------------------------------------------------------

@dataclass
class QuestionScore:
    question_id: str
    question_text: str
    competency: str
    score: int          # 1-5, or 1 if skipped
    score_rationale: str
    follow_up_count: int
    skipped: bool = False


@dataclass
class Report:
    session_id: str
    skill_pack_id: str
    skill_pack_name: str
    template: str               # scorecard | discovery-brief | audit-log | coaching-report
    generated_at: datetime
    duration_minutes: float
    scores: list[QuestionScore]
    competency_summary: dict[str, float]    # competency -> average score
    recommendation: Optional[str]           # "hire" | "no-hire" | None
    transcript: Optional[list[dict]]        # [{speaker, text, timestamp_ms}] or None
    questions_not_reached: list[str]        # question IDs not reached


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _all_questions(skill_pack: dict) -> list[dict]:
    """Return a flat list of all question dicts from all sections."""
    questions = []
    for section in skill_pack.get("sections", []):
        questions.extend(section.get("questions", []))
    return questions


def _build_scores(
    session_summary,
    skill_pack: dict,
) -> list[QuestionScore]:
    """Build the list of QuestionScore objects from the session summary.

    Rules:
    - Questions in questions_not_reached are skipped (not included in scores).
    - Questions reached but missing from summary scores (skipped due to
      max_follow_ups) get score=1, rationale="insufficient response", skipped=True.
    - Questions present in summary scores use the provided score/rationale.
    """
    # Index summary scores by question_id for O(1) lookup
    score_by_qid: dict[str, dict] = {
        s["question_id"]: s for s in (session_summary.scores or [])
    }
    not_reached: set[str] = set(session_summary.questions_not_reached or [])

    question_scores: list[QuestionScore] = []

    for q in _all_questions(skill_pack):
        qid = q["id"]

        # Questions not reached due to max_duration — omit from scores list
        if qid in not_reached:
            continue

        if qid in score_by_qid:
            entry = score_by_qid[qid]
            # Count follow-ups from transcript turns for this question
            follow_up_count = sum(
                1 for t in (session_summary.transcript or [])
                if t.get("question_id") == qid and t.get("speaker", "").lower() == "vero"
            )
            question_scores.append(
                QuestionScore(
                    question_id=qid,
                    question_text=q.get("text", ""),
                    competency=entry.get("competency", q.get("competency", "")),
                    score=entry.get("score", 1),
                    score_rationale=entry.get("rationale", ""),
                    follow_up_count=max(0, follow_up_count - 1),  # subtract initial ask
                )
            )
        else:
            # Reached but no score recorded — skipped due to max_follow_ups
            question_scores.append(
                QuestionScore(
                    question_id=qid,
                    question_text=q.get("text", ""),
                    competency=q.get("competency", ""),
                    score=1,
                    score_rationale="insufficient response",
                    follow_up_count=0,
                    skipped=True,
                )
            )

    return question_scores


def _competency_summary(scores: list[QuestionScore]) -> dict[str, float]:
    """Compute average score per competency from the scored questions."""
    totals: dict[str, list[int]] = {}
    for qs in scores:
        totals.setdefault(qs.competency, []).append(qs.score)
    return {comp: sum(vals) / len(vals) for comp, vals in totals.items()}


def _recommendation(competency_summary: dict[str, float]) -> str:
    """Return 'hire' if average competency score >= 3.5, else 'no-hire'."""
    if not competency_summary:
        return "no-hire"
    overall = sum(competency_summary.values()) / len(competency_summary)
    return "hire" if overall >= 3.5 else "no-hire"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_report(
    session_summary,
    skill_pack: dict,
    session_id: str,
    duration_minutes: float = 0.0,
) -> Report:
    """Generate a Report from a completed session summary and its Skill Pack.

    Args:
        session_summary: A SessionSummaryMessage (or compatible object) with
            .scores, .transcript, and .questions_not_reached attributes.
        skill_pack: The parsed Skill Pack dict.
        session_id: The session identifier.
        duration_minutes: Elapsed session duration in minutes.

    Returns:
        A populated Report dataclass.
    """
    template: str = skill_pack.get("report", {}).get("template", "scorecard")
    include_transcript: bool = skill_pack.get("report", {}).get("include_transcript", False)

    scores = _build_scores(session_summary, skill_pack)
    comp_summary = _competency_summary(scores)

    # Hire/no-hire recommendation only for scorecard template
    recommendation: Optional[str] = None
    if template == "scorecard":
        recommendation = _recommendation(comp_summary)

    # Transcript — only included when include_transcript is True
    transcript: Optional[list[dict]] = None
    if include_transcript and session_summary.transcript:
        transcript = [
            {
                "speaker": t.get("speaker", ""),
                # Node.js summary uses "transcript" key; older paths used "text"
                "text": t.get("transcript") or t.get("text", ""),
                "timestamp_ms": t.get("timestamp_ms", 0),
            }
            for t in session_summary.transcript
        ]

    return Report(
        session_id=session_id,
        skill_pack_id=skill_pack.get("skill", {}).get("id", ""),
        skill_pack_name=skill_pack.get("skill", {}).get("name", ""),
        template=template,
        generated_at=datetime.now(tz=timezone.utc),
        duration_minutes=duration_minutes,
        scores=scores,
        competency_summary=comp_summary,
        recommendation=recommendation,
        transcript=transcript,
        questions_not_reached=list(session_summary.questions_not_reached or []),
    )


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------

import asyncio
import dataclasses
import logging
import os
from typing import Optional as _Optional  # avoid shadowing the top-level Optional

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.models import Report as ReportORM

logger = logging.getLogger(__name__)


def _report_email_body(report: Report, skill_pack: dict) -> str:
    """Build a plain-text email body from the report."""
    lines: list[str] = []
    skill_name = report.skill_pack_name or skill_pack.get("skill", {}).get("name", "")
    lines.append(f"Session Report: {skill_name}")
    lines.append(f"Session ID: {report.session_id}")
    lines.append(f"Template: {report.template}")
    lines.append(f"Duration: {report.duration_minutes:.1f} minutes")
    lines.append(f"Generated: {report.generated_at.isoformat()}")
    lines.append("")

    if report.recommendation:
        lines.append(f"Recommendation: {report.recommendation.upper()}")
        lines.append("")

    if report.competency_summary:
        lines.append("Competency Summary:")
        for comp, avg in report.competency_summary.items():
            lines.append(f"  {comp}: {avg:.1f}/5")
        lines.append("")

    if report.scores:
        lines.append("Question Scores:")
        for qs in report.scores:
            status = " [skipped]" if qs.skipped else ""
            lines.append(f"  [{qs.score}/5]{status} {qs.question_text}")
            lines.append(f"    Rationale: {qs.score_rationale}")
        lines.append("")

    if report.questions_not_reached:
        lines.append(f"Questions not reached: {', '.join(report.questions_not_reached)}")

    return "\n".join(lines)


def _report_teams_summary(report: Report, skill_pack: dict) -> str:
    """Build a short text summary for the Teams chat post."""
    skill_name = report.skill_pack_name or skill_pack.get("skill", {}).get("name", "")
    parts = [f"📋 Vero Session Report — {skill_name}"]
    if report.recommendation:
        emoji = "✅" if report.recommendation == "hire" else "❌"
        parts.append(f"{emoji} Recommendation: {report.recommendation.upper()}")
    if report.competency_summary:
        avg_overall = sum(report.competency_summary.values()) / len(report.competency_summary)
        parts.append(f"Overall average score: {avg_overall:.1f}/5")
    parts.append(f"Session ID: {report.session_id}")
    return "\n".join(parts)


async def _send_resend_email(
    client: httpx.AsyncClient,
    api_key: str,
    to_address: str,
    subject: str,
    body: str,
) -> bool:
    """POST one email via Resend. Returns True on success."""
    payload = {
        "from": "noreply@incepta.ai",
        "to": [to_address],
        "subject": subject,
        "text": body,
    }
    try:
        resp = await client.post(
            "https://api.resend.com/emails",
            json=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )
        if resp.status_code in (200, 201):
            logger.info("Resend: email sent to %s (status %s)", to_address, resp.status_code)
            return True
        logger.warning(
            "Resend: unexpected status %s for %s — %s",
            resp.status_code, to_address, resp.text[:200],
        )
        return False
    except Exception as exc:
        logger.warning("Resend: request failed for %s — %s", to_address, exc)
        return False


async def _post_teams_summary(
    client: httpx.AsyncClient,
    conversation_id: _Optional[str],
    summary_text: str,
) -> bool:
    """Post a text summary to the Teams meeting chat via Bot Framework REST API.

    Returns True if the post succeeded, False otherwise.
    """
    bot_app_id = os.environ.get("TEAMS_BOT_APP_ID", "")
    bot_app_password = os.environ.get("TEAMS_BOT_APP_PASSWORD", "")

    if not conversation_id:
        logger.warning(
            "Teams summary: no conversation_id available — skipping chat post"
        )
        return False

    if not bot_app_id or not bot_app_password:
        logger.warning(
            "Teams summary: TEAMS_BOT_APP_ID or TEAMS_BOT_APP_PASSWORD not set — skipping"
        )
        return False

    # Acquire Bot Framework access token
    try:
        token_resp = await client.post(
            "https://login.microsoftonline.com/botframework.com/oauth2/v2.0/token",
            data={
                "grant_type": "client_credentials",
                "client_id": bot_app_id,
                "client_secret": bot_app_password,
                "scope": "https://api.botframework.com/.default",
            },
            timeout=15.0,
        )
        token_resp.raise_for_status()
        access_token = token_resp.json()["access_token"]
    except Exception as exc:
        logger.warning("Teams summary: failed to acquire Bot Framework token — %s", exc)
        return False

    # Post activity to the conversation
    activity_url = (
        f"https://smba.trafficmanager.net/apis/v3/conversations"
        f"/{conversation_id}/activities"
    )
    try:
        post_resp = await client.post(
            activity_url,
            json={"type": "message", "text": summary_text},
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            timeout=15.0,
        )
        if post_resp.status_code in (200, 201):
            logger.info("Teams summary: posted to conversation %s", conversation_id)
            return True
        logger.warning(
            "Teams summary: unexpected status %s — %s",
            post_resp.status_code, post_resp.text[:200],
        )
        return False
    except Exception as exc:
        logger.warning("Teams summary: failed to post activity — %s", exc)
        return False


async def deliver_report(
    report: Report,
    skill_pack: dict,
    db: AsyncSession,
    conversation_id: _Optional[str] = None,
) -> None:
    """Deliver the report via Resend email and Bot Framework Teams summary,
    then persist the delivery flags to the ``reports`` table.

    - Sends one Resend email per address in ``skill_pack["report"]["email_to"]``.
    - On failure, retries once after 30 seconds.
    - Posts a text summary to the Teams meeting chat if ``conversation_id`` is provided.
    - Upserts the Report ORM row with ``email_sent`` and ``chat_posted`` flags.

    Requirements: 12.6, 12.7, 12.8
    """
    api_key = os.environ.get("RESEND_API_KEY", "")
    email_to: list[str] = skill_pack.get("report", {}).get("email_to", [])
    skill_name = skill_pack.get("skill", {}).get("name", "")
    subject = f"Vero Session Report: {skill_name}"
    body = _report_email_body(report, skill_pack)
    summary_text = _report_teams_summary(report, skill_pack)

    email_sent = False
    chat_posted = False

    async with httpx.AsyncClient() as client:
        # ------------------------------------------------------------------ #
        # Resend delivery — one request per recipient, one retry on failure   #
        # ------------------------------------------------------------------ #
        if not api_key:
            logger.warning("deliver_report: RESEND_API_KEY not set — skipping email delivery")
        elif not email_to:
            logger.warning("deliver_report: skill_pack.report.email_to is empty — no emails sent")
        else:
            all_sent = True
            for address in email_to:
                logger.info("Resend: attempting delivery to %s (attempt 1)", address)
                success = await _send_resend_email(client, api_key, address, subject, body)
                if not success:
                    logger.warning(
                        "Resend: first attempt failed for %s — retrying in 30s", address
                    )
                    await asyncio.sleep(30)
                    logger.info("Resend: retrying delivery to %s (attempt 2)", address)
                    success = await _send_resend_email(client, api_key, address, subject, body)
                    if not success:
                        logger.error(
                            "Resend: retry also failed for %s — giving up", address
                        )
                        all_sent = False
            email_sent = all_sent

        # ------------------------------------------------------------------ #
        # Bot Framework Teams summary                                         #
        # ------------------------------------------------------------------ #
        chat_posted = await _post_teams_summary(client, conversation_id, summary_text)

    # ---------------------------------------------------------------------- #
    # Persist / upsert the Report ORM row                                     #
    # ---------------------------------------------------------------------- #
    report_content = dataclasses.asdict(report)
    # datetime objects are not JSON-serialisable by default — convert to ISO strings
    report_content["generated_at"] = report.generated_at.isoformat()

    result = await db.execute(
        select(ReportORM).where(ReportORM.session_id == report.session_id)
    )
    existing: _Optional[ReportORM] = result.scalar_one_or_none()

    if existing is not None:
        existing.template = report.template
        existing.content = report_content
        existing.generated_at = report.generated_at
        existing.email_sent = email_sent
        existing.chat_posted = chat_posted
    else:
        db.add(
            ReportORM(
                session_id=report.session_id,
                template=report.template,
                content=report_content,
                generated_at=report.generated_at,
                email_sent=email_sent,
                chat_posted=chat_posted,
            )
        )

    await db.commit()
    logger.info(
        "deliver_report: persisted report for session %s "
        "(email_sent=%s, chat_posted=%s)",
        report.session_id, email_sent, chat_posted,
    )

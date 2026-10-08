"""Session lifecycle management — create, update, and retrieve session state.

NOTE: This module now uses the database as the single source of truth.
In-memory caches have been removed to support multi-instance deployments.
Pipeline registry uses Redis when available, with fallback to in-memory.
"""
from __future__ import annotations

import logging
import os
import socket
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from types import SimpleNamespace
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db import get_db
from backend.models import Session as SessionModel
from backend.recall_client import create_bot
from backend.redis_client import (
    get_pipeline_redis,
    register_pipeline_redis,
    unregister_pipeline_redis,
    store_session_summary_redis,
    get_session_summary_redis,
)
from backend.skill_pack_validator import validate_skill_pack

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Active pipeline registry (keyed by session_id)
# Uses Redis for multi-instance deployments, with in-memory fallback.
# ---------------------------------------------------------------------------

_active_pipelines: dict[str, Any] = {}


def _get_pipeline_info(pipeline: Any) -> dict:
    """Extract serializable pipeline info for Redis storage."""
    return {
        "host": socket.gethostname(),
        "pid": os.getpid(),
        "started_at": datetime.now(tz=timezone.utc).isoformat(),
        "session_id": getattr(pipeline, "session_id", "unknown"),
    }


def _calculate_pipeline_ttl(skill_pack: dict) -> int:
    """Calculate Redis TTL based on skill pack max_duration_minutes.

    Returns TTL in seconds: max_duration_minutes * 60 + 600 (10 min buffer).
    Minimum TTL is 1 hour (3600 seconds).
    """
    max_duration = skill_pack.get("agent", {}).get("max_duration_minutes", 30)
    # Convert to seconds and add 10 minute buffer
    ttl = max_duration * 60 + 600
    # Ensure minimum of 1 hour
    return max(ttl, 3600)


async def register_pipeline(
    session_id: str,
    pipeline: Any,
    skill_pack: dict | None = None,
) -> None:
    """Register an active AudioPipeline instance for a session.

    Stores in both local memory (for fast access) and Redis (for multi-instance).
    Redis TTL is calculated based on skill_pack max_duration_minutes to ensure
    the pipeline entry doesn't expire mid-session.
    """
    _active_pipelines[session_id] = pipeline

    # Also register in Redis for cross-instance visibility
    pipeline_info = _get_pipeline_info(pipeline)

    # Calculate TTL based on skill pack duration (default 30 min + buffer)
    ttl_seconds = _calculate_pipeline_ttl(skill_pack or {})
    await register_pipeline_redis(session_id, pipeline_info, ttl_seconds)

    logger.info("register_pipeline[%s]: pipeline registered", session_id)


async def get_pipeline(session_id: str) -> Optional[Any]:
    """Return the active AudioPipeline for a session, or None if not found.

    First checks local memory, then Redis to find which instance has the pipeline.
    """
    # Check local memory first
    if session_id in _active_pipelines:
        return _active_pipelines[session_id]

    # Check Redis to see if another instance has this pipeline
    pipeline_info = await get_pipeline_redis(session_id)
    if pipeline_info:
        # Pipeline exists on another instance - log this for debugging
        logger.info(
            "get_pipeline[%s]: pipeline is on host=%s pid=%s (not local)",
            session_id,
            pipeline_info.get("host"),
            pipeline_info.get("pid"),
        )

    return None


def get_pipeline_local(session_id: str) -> Optional[Any]:
    """Get pipeline from local memory only (synchronous)."""
    return _active_pipelines.get(session_id)


async def unregister_pipeline(session_id: str) -> None:
    """Remove the pipeline entry for a session."""
    _active_pipelines.pop(session_id, None)
    await unregister_pipeline_redis(session_id)
    logger.info("unregister_pipeline[%s]: pipeline unregistered", session_id)


# ---------------------------------------------------------------------------
# Session summaries stored in Redis for cross-instance access
# Previously used in-memory dict which failed in multi-instance deployments.
# Now uses Redis so any instance can retrieve the summary for report generation.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# SessionState dataclasses
# ---------------------------------------------------------------------------

class SessionStatus(Enum):
    PENDING = "pending"
    JOINING = "joining"
    ACTIVE = "active"
    CLOSING = "closing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class TurnLatency:
    turn_index: int
    eou_timestamp_ms: int
    first_audio_chunk_ms: int

    @property
    def latency_ms(self) -> int:
        return self.first_audio_chunk_ms - self.eou_timestamp_ms


@dataclass
class SessionState:
    session_id: str
    skill_pack: dict
    recall_bot_id: str
    teams_meeting_url: str
    status: SessionStatus
    created_at: datetime
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    pi_agent_pid: Optional[int] = None
    turn_latencies: list = field(default_factory=list)
    tts_fallback_used: bool = False
    error: Optional[str] = None
    context_data: Optional[dict] = None  # Input data for skills with input_schema


# ---------------------------------------------------------------------------
# Session store accessors - Now using DB as single source of truth
# ---------------------------------------------------------------------------

async def get_session(session_id: str, db: AsyncSession) -> Optional[SessionState]:
    """Look up a session by ID from the database.

    Args:
        session_id: The session identifier.
        db: An active AsyncSession for DB access.

    Returns:
        SessionState if found, None otherwise.
    """
    result = await db.execute(
        select(SessionModel).where(SessionModel.session_id == session_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return None

    return SessionState(
        session_id=row.session_id,
        skill_pack=row.skill_pack,
        recall_bot_id=row.recall_bot_id or "",
        teams_meeting_url=row.meeting_url or "",
        status=SessionStatus(row.status),
        created_at=row.created_at,
        started_at=row.started_at,
        ended_at=row.ended_at,
        context_data=row.context_data,
    )


async def update_session(state: SessionState, db: AsyncSession) -> None:
    """Update session state in the database.

    Args:
        state: The session state to update.
        db: An active AsyncSession for DB access.
    """
    result = await db.execute(
        select(SessionModel).where(SessionModel.session_id == state.session_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        logger.warning("update_session[%s]: session not found in DB", state.session_id)
        return

    row.status = state.status.value
    row.started_at = state.started_at
    row.ended_at = state.ended_at
    row.error = state.error
    await db.commit()


async def add_turn_latency(
    session_id: str,
    turn_index: int,
    eou_ms: int,
    first_audio_ms: int,
    db: AsyncSession,
) -> None:
    """Persist a Turn latency record to the DB.

    Args:
        session_id: The session this turn belongs to.
        turn_index: Zero-based turn index within the session.
        eou_ms: Monotonic timestamp (ms) when EOU fired.
        first_audio_ms: Monotonic timestamp (ms) when first audio chunk was ready.
        db: An active AsyncSession for DB persistence.
    """
    from backend.models import Turn as TurnModel

    # Persist to DB (single source of truth)
    turn_row = TurnModel(
        session_id=session_id,
        turn_index=turn_index,
        speaker="",       # speaker/transcript filled by other pipeline paths
        transcript="",
        eou_ts_ms=eou_ms,
        first_audio_ts_ms=first_audio_ms,
    )
    db.add(turn_row)
    try:
        await db.commit()
        logger.debug(
            "add_turn_latency[%s]: persisted turn %d (latency=%dms)",
            session_id,
            turn_index,
            first_audio_ms - eou_ms,
        )
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        logger.warning(
            "add_turn_latency[%s]: DB commit failed for turn %d: %s",
            session_id,
            turn_index,
            exc,
        )


async def add_turn_transcript(
    session_id: str,
    turn_index: int,
    speaker: str,
    transcript: str,
    timestamp_ms: int,
    db: AsyncSession,
) -> None:
    """Persist or update a Turn with transcript data.

    Args:
        session_id: The session this turn belongs to.
        turn_index: Zero-based turn index within the session.
        speaker: Who spoke (e.g., 'agent', 'participant').
        transcript: The transcribed text.
        timestamp_ms: Timestamp in milliseconds.
        db: An active AsyncSession for DB persistence.
    """
    from backend.models import Turn as TurnModel

    # Check if turn already exists (from latency tracking)
    result = await db.execute(
        select(TurnModel).where(
            TurnModel.session_id == session_id,
            TurnModel.turn_index == turn_index
        )
    )
    turn_row = result.scalar_one_or_none()

    if turn_row:
        # Update existing turn (created by latency tracking with blank speaker/transcript)
        turn_row.speaker = speaker
        turn_row.transcript = transcript
        # eou_ts_ms stores the turn timestamp when coming from LiveKit (no latency data)
        if turn_row.eou_ts_ms is None:
            turn_row.eou_ts_ms = timestamp_ms
    else:
        # Create new turn (LiveKit path — no prior latency tracking row)
        turn_row = TurnModel(
            session_id=session_id,
            turn_index=turn_index,
            speaker=speaker,
            transcript=transcript,
            eou_ts_ms=timestamp_ms,
        )
        db.add(turn_row)

    try:
        await db.commit()
        logger.debug(
            "add_turn_transcript[%s]: persisted turn %d (speaker=%s)",
            session_id,
            turn_index,
            speaker,
        )
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        logger.warning(
            "add_turn_transcript[%s]: DB commit failed for turn %d: %s",
            session_id,
            turn_index,
            exc,
        )


# ---------------------------------------------------------------------------
# Session creation
# ---------------------------------------------------------------------------

async def create_session(
    skill_pack: dict,
    meeting_url: str,
    db: AsyncSession,
    context_data: Optional[dict] = None,
) -> SessionState:
    """Validate the Skill Pack, create a Recall.ai bot, persist to DB, and return SessionState.

    Args:
        skill_pack: Parsed Skill Pack dict (already parsed from YAML).
        meeting_url: The Teams meeting URL for the bot to join.
        db: An active AsyncSession for DB persistence.

    Returns:
        A SessionState instance with status PENDING.

    Raises:
        ValueError: If the Skill Pack fails validation.
        RecallJoinError: If the Recall.ai bot creation fails after one retry.
    """
    # Validate Skill Pack
    result = validate_skill_pack(skill_pack)
    if not result.is_valid:
        raise ValueError(result.errors)

    # Create Recall.ai bot
    api_key = os.environ["RECALL_API_KEY"]
    bot_name = skill_pack["agent"]["name"]
    recall_bot_id = await create_bot(meeting_url, bot_name, api_key)

    # Build session ID and state
    session_id = f"sess_{uuid.uuid4().hex[:12]}"
    now = datetime.now(tz=timezone.utc)

    state = SessionState(
        session_id=session_id,
        skill_pack=skill_pack,
        recall_bot_id=recall_bot_id,
        teams_meeting_url=meeting_url,
        status=SessionStatus.PENDING,
        created_at=now,
        context_data=context_data,
    )

    # Persist to DB
    db_row = SessionModel(
        session_id=session_id,
        skill_pack=skill_pack,
        recall_bot_id=recall_bot_id,
        meeting_url=meeting_url,
        status=SessionStatus.PENDING.value,
        created_at=now,
        context_data=context_data,
    )
    db.add(db_row)
    await db.commit()

    # Note: Session is now only stored in DB, not in-memory cache
    logger.info("create_session[%s]: session persisted to DB", session_id)

    return state


# ---------------------------------------------------------------------------
# Session summary store
# ---------------------------------------------------------------------------

async def store_session_summary(session_id: str, summary: dict) -> None:
    """Store a session summary dict (from the pipeline) for later report generation.

    Called by the pipeline when it receives a SessionSummaryMessage from pi_agent.
    Stores in Redis for cross-instance access - any backend instance can retrieve
    the summary when close_session is called via webhook.

    Args:
        session_id: The session this summary belongs to.
        summary: A dict representation of SessionSummaryMessage
                 (keys: scores, transcript, questions_not_reached).
    """
    # Store in Redis with 2-hour TTL (longer than max session duration)
    await store_session_summary_redis(session_id, summary, ttl_seconds=7200)
    logger.info("store_session_summary[%s]: summary stored in Redis", session_id)


async def create_phone_session(
    skill_pack: dict,
    phone_number: str,
    db: AsyncSession,
    context_data: Optional[dict] = None,
) -> SessionState:
    """Create a session for a Twilio phone call (no Recall.ai bot).

    Args:
        skill_pack: Parsed Skill Pack dict.
        phone_number: E.164 number to dial.
        db: An active AsyncSession for DB persistence.

    Returns:
        A SessionState with status PENDING and recall_bot_id="".
    """
    result = validate_skill_pack(skill_pack)
    if not result.is_valid:
        raise ValueError(result.errors)

    session_id = f"sess_{uuid.uuid4().hex[:12]}"
    now = datetime.now(tz=timezone.utc)

    state = SessionState(
        session_id=session_id,
        skill_pack=skill_pack,
        recall_bot_id="",
        teams_meeting_url="",
        status=SessionStatus.PENDING,
        created_at=now,
        context_data=context_data,
    )

    db_row = SessionModel(
        session_id=session_id,
        skill_pack=skill_pack,
        recall_bot_id=None,
        meeting_url="",
        status=SessionStatus.PENDING.value,
        created_at=now,
        channel="phone",
        phone_number=phone_number,
        context_data=context_data,
    )
    db.add(db_row)
    await db.commit()

    # Note: Session is now only stored in DB
    return state


# ---------------------------------------------------------------------------
# Full transcript builder
# ---------------------------------------------------------------------------

async def _build_and_store_full_transcript(session_id: str, db: AsyncSession) -> None:
    """Build full transcript from turns and store in session."""
    from backend.models import Turn as TurnModel, Session as SessionModel
    from sqlalchemy import select

    try:
        result = await db.execute(
            select(TurnModel)
            .where(TurnModel.session_id == session_id)
            .order_by(TurnModel.turn_index)
        )
        turns = result.scalars().all()

        if not turns:
            return

        lines = []
        for turn in turns:
            speaker_label = "Agent" if turn.speaker == "agent" else "User"
            lines.append(f"{speaker_label}: {turn.transcript}")

        full_transcript = "\n\n".join(lines)

        result = await db.execute(
            select(SessionModel).where(SessionModel.session_id == session_id)
        )
        session_row = result.scalar_one_or_none()

        if session_row:
            session_row.full_transcript = full_transcript
            await db.commit()
            logger.info(
                "_build_full_transcript[%s]: stored transcript with %d turns",
                session_id,
                len(turns)
            )
    except Exception as exc:
        logger.error("_build_full_transcript[%s]: failed: %s", session_id, exc)
        await db.rollback()


# ---------------------------------------------------------------------------
# Session close flow
# ---------------------------------------------------------------------------

async def close_session(
    session_id: str,
    db: AsyncSession,
    conversation_id: Optional[str] = None,
) -> None:
    """Close a session: generate and deliver the report, then update status.

    Reads the session summary stored by the pipeline via store_session_summary.
    If no summary is available, generates a minimal empty summary.

    - Records ended_at and calculates duration_minutes.
    - For phone calls: hangs up the Twilio call if active.
    - Calls generate_report() then deliver_report().
    - Transitions session status to COMPLETED on success.
    - Transitions to FAILED (with partial report attempt) on unrecoverable error.
    - Logs a warning if total elapsed time exceeds 60 seconds.

    Requirements: 12.1, 12.2

    Args:
        session_id: The session to close.
        db: An active AsyncSession for DB persistence.
        conversation_id: Optional Teams conversation ID for chat summary posting.
    """
    from backend.report_generator import deliver_report, generate_report
    from sqlalchemy import select

    close_start = time.monotonic()

    # ------------------------------------------------------------------
    # Load session state and DB row
    # ------------------------------------------------------------------
    now = datetime.now(tz=timezone.utc)

    # Fetch DB row early (needed for hangup and report generation)
    from backend.models import Session as SessionModel
    result = await db.execute(
        select(SessionModel).where(SessionModel.session_id == session_id)
    )
    session_row = result.scalar_one_or_none()

    if session_row is None:
        logger.error("close_session[%s]: session not found in DB", session_id)
        return

    # ------------------------------------------------------------------
    # Hang up phone calls if active and fetch recording URL
    # ------------------------------------------------------------------
    if session_row.channel == "phone" and session_row.twilio_call_sid:
        try:
            from backend.mcp.twilio_client import get_twilio_mcp_client
            client = get_twilio_mcp_client()
            await client.hangup_call(session_row.twilio_call_sid)
            logger.info("close_session[%s]: hung up Twilio call %s", session_id, session_row.twilio_call_sid)
        except Exception as exc:
            logger.warning("close_session[%s]: failed to hang up call: %s", session_id, exc)

        # Fetch recording URL for phone calls
        try:
            from backend.mcp.twilio_client import get_twilio_mcp_client
            client = get_twilio_mcp_client()
            recordings = await client.get_recordings(session_row.twilio_call_sid)
            if recordings and len(recordings) > 0:
                # Get the first recording URL
                recording = recordings[0]
                session_row.recording_url = recording.get("uri", "").replace(".json", ".mp3")
                logger.info("close_session[%s]: fetched recording URL %s", session_id, session_row.recording_url)
        except Exception as exc:
            logger.warning("close_session[%s]: failed to fetch recording URL: %s", session_id, exc)

    # session_row already loaded above

    skill_pack: dict = session_row.skill_pack or {}
    started_at: Optional[datetime] = session_row.started_at

    # Calculate duration
    if started_at is not None:
        # Ensure both datetimes are timezone-aware for subtraction
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)
        duration_minutes = (now - started_at).total_seconds() / 60.0
    else:
        duration_minutes = 0.0

    # ------------------------------------------------------------------
    # Build full transcript from turns
    # ------------------------------------------------------------------
    await _build_and_store_full_transcript(session_id, db)

    # ------------------------------------------------------------------
    # Build session_summary object from Redis (or empty fallback)
    # ------------------------------------------------------------------
    # Retrieve from Redis (cross-instance safe) - deletes after reading
    summary_dict = await get_session_summary_redis(session_id)
    if summary_dict is None:
        logger.warning(
            "close_session[%s]: no session summary available in Redis — using empty summary",
            session_id,
        )
        summary_dict = {
            "scores": [],
            "transcript": [],
            "questions_not_reached": [],
        }

    # Build full transcript from turns before closing
    await _build_and_store_full_transcript(session_id, db)

    # Wrap dict in a SimpleNamespace so generate_report can access .scores etc.
    session_summary = SimpleNamespace(
        scores=summary_dict.get("scores", []),
        transcript=summary_dict.get("transcript", []),
        questions_not_reached=summary_dict.get("questions_not_reached", []),
    )

    # ------------------------------------------------------------------
    # Generate and deliver report
    # ------------------------------------------------------------------
    try:
        report = generate_report(session_summary, skill_pack, session_id, duration_minutes)
        await deliver_report(report, skill_pack, db, conversation_id)

        # Transition to COMPLETED
        session_row.status = SessionStatus.COMPLETED.value
        session_row.ended_at = now
        await db.commit()

        logger.info("close_session[%s]: session COMPLETED", session_id)

    except Exception as exc:  # noqa: BLE001
        logger.error(
            "close_session[%s]: unrecoverable error during report generation/delivery: %s",
            session_id,
            exc,
            exc_info=True,
        )

        # Attempt to persist a partial report marker
        try:
            from backend.models import Report as ReportORM
            from sqlalchemy import select as sa_select
            import dataclasses
            from backend.report_generator import generate_report as _gen

            partial_report = _gen(session_summary, skill_pack, session_id, duration_minutes)
            partial_content = dataclasses.asdict(partial_report)
            partial_content["generated_at"] = partial_report.generated_at.isoformat()
            partial_content["partial"] = True

            rpt_result = await db.execute(
                sa_select(ReportORM).where(ReportORM.session_id == session_id)
            )
            existing_rpt = rpt_result.scalar_one_or_none()
            if existing_rpt is None:
                db.add(ReportORM(
                    session_id=session_id,
                    template=partial_report.template,
                    content=partial_content,
                    generated_at=partial_report.generated_at,
                    email_sent=False,
                    chat_posted=False,
                ))
            await db.commit()
        except Exception as partial_exc:  # noqa: BLE001
            logger.error(
                "close_session[%s]: failed to persist partial report: %s",
                session_id,
                partial_exc,
            )
            await db.rollback()

        # Transition to FAILED
        try:
            session_row.status = SessionStatus.FAILED.value
            session_row.ended_at = now
            session_row.error = str(exc)
            await db.commit()
        except Exception:  # noqa: BLE001
            await db.rollback()

        logger.error("close_session[%s]: session FAILED", session_id)

    finally:
        elapsed = time.monotonic() - close_start
        if elapsed > 60.0:
            logger.warning(
                "close_session[%s]: report generation+delivery took %.1fs — exceeded 60s budget",
                session_id,
                elapsed,
            )
        else:
            logger.info(
                "close_session[%s]: close flow completed in %.1fs", session_id, elapsed
            )

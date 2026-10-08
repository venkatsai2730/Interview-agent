"""Sessions router - session lifecycle management."""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Security, UploadFile, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import verify_token, security, _constant_time_compare
from fastapi.security import HTTPAuthorizationCredentials
from backend.db import get_db
from backend.models import Session as SessionModel, Report as ReportModel, Turn as TurnModel
from backend.schemas import (
    CreateSessionRequest,
    CreatePhoneSessionRequest,
    CreateLiveKitPhoneRequest,
    SessionListResponse,
)
from backend.session_manager import create_session, create_phone_session
from backend.skill_pack_validator import ParseError, parse_skill_pack_yaml, validate_skill_pack

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sessions", tags=["sessions"])


async def _get_db():
    """Dependency to get DB session."""
    async for session in get_db():
        yield session


# ---------------------------------------------------------------------------
# PDF Upload + Weightage Analysis endpoint
# ---------------------------------------------------------------------------

@router.post("/analyze-resume")
async def analyze_resume_endpoint(
    resume: UploadFile = File(...),
    job_description: UploadFile = File(None),
    job_description_text: Optional[str] = None,
    token: str = Depends(verify_token),
):
    """Upload resume PDF (and optionally JD PDF), run weightage analysis.

    Returns structured analysis to be injected into context_data when creating a session.
    Accepts:
      - resume: PDF file (required)
      - job_description: PDF file (optional, alternative to text)
      - job_description_text: Plain text JD (optional, used if no PDF provided)
    """
    from backend.weightage_analyzer import analyze_resume_jd, extract_pdf_text

    # Extract resume text from PDF
    if not resume.filename or not resume.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Resume must be a PDF file")

    resume_bytes = await resume.read()
    if len(resume_bytes) > 10 * 1024 * 1024:  # 10MB limit
        raise HTTPException(status_code=400, detail="Resume PDF too large (max 10MB)")

    try:
        resume_text = await extract_pdf_text(resume_bytes)
    except Exception as exc:
        logger.error("Failed to extract text from resume PDF: %s", exc)
        raise HTTPException(status_code=422, detail=f"Could not read resume PDF: {exc}")

    if not resume_text.strip():
        raise HTTPException(status_code=422, detail="Resume PDF appears to be empty or image-only (no extractable text)")

    # Extract JD text (from PDF or plain text)
    jd_text = ""
    if job_description and job_description.filename:
        jd_bytes = await job_description.read()
        try:
            jd_text = await extract_pdf_text(jd_bytes)
        except Exception as exc:
            logger.warning("Failed to extract JD PDF text: %s, using empty", exc)
    if not jd_text and job_description_text:
        jd_text = job_description_text

    if not jd_text.strip():
        raise HTTPException(status_code=400, detail="Job description is required (provide PDF or text)")

    # Run the weightage analysis
    logger.info("analyze_resume: running weightage analysis (resume=%d chars, jd=%d chars)",
                len(resume_text), len(jd_text))

    analysis = await analyze_resume_jd(resume_text, jd_text)

    return {
        "analysis": analysis,
        "resume_text": resume_text[:2000] + "..." if len(resume_text) > 2000 else resume_text,
        "jd_text": jd_text[:2000] + "..." if len(jd_text) > 2000 else jd_text,
    }


class SessionListItem(BaseModel):
    session_id: str
    skill_pack_name: Optional[str]
    skill_pack_id: Optional[str]
    status: str
    channel: Optional[str]
    created_at: datetime
    started_at: Optional[datetime]
    ended_at: Optional[datetime]
    duration_minutes: Optional[float]
    has_report: bool
    recording_url: Optional[str]
    recall_recording_url: Optional[str]


class SessionListResponse(BaseModel):
    items: list[SessionListItem]
    total: int
    page: int
    page_size: int


@router.post("/", status_code=201)
async def create_session_endpoint(
    request: CreateSessionRequest,
    db: AsyncSession = Depends(_get_db),
    token: str = Depends(verify_token),
):
    """Create a new session: validate Skill Pack, trigger Recall.ai bot join."""
    from backend.models import SkillPack as SkillPackModel
    from backend.recall_client import InvalidMeetingUrlError, RecallJoinError

    yaml_content: Optional[str] = None

    if request.skill_pack_id is not None:
        sp_result = await db.execute(
            select(SkillPackModel).where(SkillPackModel.id == request.skill_pack_id)
        )
        sp_row = sp_result.scalar_one_or_none()
        if sp_row is None:
            raise HTTPException(
                status_code=404,
                detail=f"Skill Pack '{request.skill_pack_id}' not found",
            )
        yaml_content = sp_row.yaml_content
    elif request.yaml_content is not None:
        yaml_content = request.yaml_content
    else:
        active_result = await db.execute(
            select(SkillPackModel).where(SkillPackModel.is_active == True)  # noqa: E712
        )
        active_row = active_result.scalar_one_or_none()
        if active_row is None:
            raise HTTPException(
                status_code=400,
                detail="No skill_pack_id provided and no active Skill Pack found",
            )
        yaml_content = active_row.yaml_content

    try:
        parsed = parse_skill_pack_yaml(yaml_content)
    except ParseError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"YAML parse error at line {exc.line}: {exc.message}",
        ) from exc

    result = validate_skill_pack(parsed)
    if not result.is_valid:
        raise HTTPException(
            status_code=422,
            detail={"message": "Validation failed", "errors": result.errors},
        )
    
    # Apply overrides
    if request.tts_voice:
        parsed.setdefault("agent", {})['tts_voice'] = request.tts_voice
    if request.llm_model:
        agent = parsed.setdefault("agent", {})
        prefs = agent.setdefault("model_preferences", [{}])
        if prefs:
            prefs[0]['model'] = request.llm_model
    if request.agent_name:
        parsed.setdefault("agent", {})['name'] = request.agent_name
    if request.context_data:
        parsed['context_data'] = request.context_data
    if request.language:
        parsed.setdefault("agent", {})['language'] = request.language

    # Filter sections by selected mode (_mode in context_data)
    if request.context_data and '_mode' in request.context_data:
        selected_mode = request.context_data['_mode']
        all_sections = parsed.get('sections', [])
        filtered = [s for s in all_sections if s.get('mode', '') == selected_mode]
        if filtered:
            parsed['sections'] = filtered

    try:
        session_state = await create_session(parsed, request.meeting_url, db, context_data=request.context_data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"message": "Validation failed", "errors": exc.args[0]})
    except InvalidMeetingUrlError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid or expired meeting URL: {exc.message}")
    except RecallJoinError as exc:
        raise HTTPException(status_code=503, detail=f"Failed to join meeting via Recall.ai: {exc.message}")

    # Start background poller
    asyncio.ensure_future(_poll_bot_until_active(session_state.session_id, session_state.recall_bot_id, parsed))

    return {"session_id": session_state.session_id, "status": "pending"}


@router.get("/", response_model=SessionListResponse)
async def list_sessions_endpoint(
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(_get_db),
    token: str = Depends(verify_token),
):
    """Return a paginated list of sessions with summary fields."""
    # Build base WHERE clause
    base_filter = []
    if status is not None:
        base_filter.append(SessionModel.status == status)

    # Total count query
    count_stmt = select(func.count()).select_from(SessionModel)
    if base_filter:
        count_stmt = count_stmt.where(*base_filter)
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    # Paginated rows
    offset = (page - 1) * page_size
    rows_stmt = (
        select(SessionModel)
        .order_by(SessionModel.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    if base_filter:
        rows_stmt = rows_stmt.where(*base_filter)

    rows_result = await db.execute(rows_stmt)
    rows = rows_result.scalars().all()

    # Check which sessions have reports
    session_ids = [row.session_id for row in rows]
    reports_result = await db.execute(
        select(ReportModel.session_id).where(ReportModel.session_id.in_(session_ids))
    )
    has_report_set = set(reports_result.scalars().all())

    items = []
    for row in rows:
        skill_pack = row.skill_pack or {}
        duration = None
        if row.started_at and row.ended_at:
            duration = (row.ended_at - row.started_at).total_seconds() / 60.0

        items.append(
            SessionListItem(
                session_id=row.session_id,
                skill_pack_name=skill_pack.get("skill", {}).get("name"),
                skill_pack_id=skill_pack.get("skill", {}).get("id"),
                status=row.status,
                channel=row.channel,
                created_at=row.created_at,
                started_at=row.started_at,
                ended_at=row.ended_at,
                duration_minutes=duration,
                has_report=row.session_id in has_report_set,
                recording_url=row.recording_url,
                recall_recording_url=row.recall_recording_url,
            )
        )

    return SessionListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/{session_id}")
async def get_session_endpoint(
    session_id: str,
    db: AsyncSession = Depends(_get_db),
    token: str = Depends(verify_token),
):
    """Return session status, turn count, latency metrics, and report status."""
    # Look up session
    result = await db.execute(
        select(SessionModel).where(SessionModel.session_id == session_id)
    )
    session_row = result.scalar_one_or_none()
    if session_row is None:
        raise HTTPException(status_code=404, detail="Session not found")

    # Fetch all turn records
    turns_result = await db.execute(
        select(TurnModel).where(TurnModel.session_id == session_id)
    )
    turn_rows = turns_result.scalars().all()

    # Latency calculations
    latencies = [
        row.first_audio_ts_ms - row.eou_ts_ms
        for row in turn_rows
        if row.eou_ts_ms is not None and row.first_audio_ts_ms is not None
    ]

    def _calculate_percentile(values: list, percentile: int) -> Optional[float]:
        if not values:
            return None
        sorted_vals = sorted(values)
        k = (len(sorted_vals) - 1) * percentile / 100
        f = int(k)
        c = f + 1 if f + 1 < len(sorted_vals) else f
        return sorted_vals[f] + (k - f) * (sorted_vals[c] - sorted_vals[f])

    p50 = _calculate_percentile(latencies, 50)
    p90 = _calculate_percentile(latencies, 90)

    # Report delivery status
    report_result = await db.execute(
        select(ReportModel).where(ReportModel.session_id == session_id)
    )
    report_row = report_result.scalar_one_or_none()

    skill_pack = session_row.skill_pack or {}
    agent = skill_pack.get("agent", {})

    # Calculate elapsed time
    elapsed_seconds = None
    if session_row.started_at:
        ended_at = session_row.ended_at or datetime.now(tz=timezone.utc)
        elapsed_seconds = int((ended_at - session_row.started_at).total_seconds())

    # Current question info
    current_question_text = None
    current_question_index = None

    return {
        "session_id": session_row.session_id,
        "status": session_row.status,
        "skill_pack_name": skill_pack.get("skill", {}).get("name"),
        "turn_count": len(turn_rows),
        "p50_latency_ms": p50,
        "p90_latency_ms": p90,
        "report_delivered": report_row is not None,
        "email_sent": report_row.email_sent if report_row else False,
        "chat_posted": report_row.chat_posted if report_row else False,
        "current_question_text": current_question_text,
        "current_question_index": current_question_index,
        "elapsed_seconds": elapsed_seconds,
        "turn_latencies": [
            {"turn_index": row.turn_index, "latency_ms": row.first_audio_ts_ms - row.eou_ts_ms}
            for row in turn_rows
            if row.eou_ts_ms is not None and row.first_audio_ts_ms is not None
        ],
        "agent_name": agent.get("name"),
        "tts_voice": agent.get("tts_voice"),
    }


@router.post("/phone", status_code=201)
async def create_phone_session_endpoint(
    request: CreatePhoneSessionRequest,
    db: AsyncSession = Depends(_get_db),
    token: str = Depends(verify_token),
):
    """Create a session and place an outbound Twilio call to phone_number."""
    from backend.models import SkillPack as SkillPackModel
    from backend.mcp.twilio_client import get_twilio_mcp_client

    # Resolve skill pack
    if request.skill_pack_id:
        sp_result = await db.execute(
            select(SkillPackModel).where(SkillPackModel.id == request.skill_pack_id)
        )
        sp_row = sp_result.scalar_one_or_none()
        if sp_row is None:
            raise HTTPException(status_code=404, detail="Skill Pack not found")
        yaml_content = sp_row.yaml_content
    else:
        active_result = await db.execute(
            select(SkillPackModel).where(SkillPackModel.is_active == True)  # noqa: E712
        )
        active_row = active_result.scalar_one_or_none()
        if active_row is None:
            raise HTTPException(status_code=400, detail="No skill_pack_id provided and no active Skill Pack")
        yaml_content = active_row.yaml_content

    try:
        parsed = parse_skill_pack_yaml(yaml_content)
    except ParseError as exc:
        raise HTTPException(status_code=422, detail=f"YAML parse error: {exc.message}")

    result = validate_skill_pack(parsed)
    if not result.is_valid:
        raise HTTPException(status_code=422, detail={"message": "Validation failed", "errors": result.errors})

    # Apply overrides
    if request.tts_voice:
        parsed.setdefault("agent", {})["tts_voice"] = request.tts_voice
    if request.llm_model:
        agent = parsed.setdefault("agent", {})
        prefs = agent.setdefault("model_preferences", [{}])
        if prefs:
            prefs[0]["model"] = request.llm_model
    if request.agent_name:
        parsed.setdefault("agent", {})["name"] = request.agent_name
    if request.context_data:
        parsed["context_data"] = request.context_data

    # Filter sections by selected mode (_mode in context_data)
    if request.context_data and '_mode' in request.context_data:
        selected_mode = request.context_data['_mode']
        all_sections = parsed.get('sections', [])
        filtered = [s for s in all_sections if s.get('mode', '') == selected_mode]
        if filtered:
            parsed['sections'] = filtered

    # Mark as phone channel
    parsed["channel"] = "phone"

    # Create session
    session_state = await create_phone_session(parsed, request.phone_number, db, context_data=request.context_data)

    # Place the call via Twilio MCP with recording enabled
    try:
        twiml_url = f"{os.environ.get('WEBHOOK_URL', '')}/twilio/livekit-bridge?session_id={session_state.session_id}"
        recording_callback = f"{os.environ.get('WEBHOOK_URL', '')}/twilio/recording-callback"
        client = get_twilio_mcp_client()
        call_sid = await client.create_call(
            to_number=request.phone_number,
            twiml_url=twiml_url,
            record=True,
            recording_status_callback=recording_callback,
        )
        logger.info("Created Twilio call %s for session %s", call_sid, session_state.session_id)

        # Store the Twilio call SID in the database
        from sqlalchemy import update as _update
        await db.execute(
            _update(SessionModel)
            .where(SessionModel.session_id == session_state.session_id)
            .values(twilio_call_sid=call_sid)
        )
        await db.commit()
    except Exception as exc:
        logger.error("Failed to create Twilio call: %s", exc)
        raise HTTPException(status_code=503, detail=f"Failed to place call: {exc}")

    return {"session_id": session_state.session_id, "status": "pending"}


@router.post("/phone-livekit", status_code=201)
async def create_livekit_phone_session(
    request: CreateLiveKitPhoneRequest,
    db: AsyncSession = Depends(_get_db),
    token: str = Depends(verify_token),
):
    """Create a session and place an outbound call via LiveKit SIP + Twilio trunk."""
    from backend.livekit_client import create_sip_outbound_call
    from backend.models import SkillPack as SkillPackModel

    sip_trunk_id = os.environ.get("LIVEKIT_SIP_TRUNK_ID", "")
    if not sip_trunk_id:
        raise HTTPException(status_code=503, detail="LIVEKIT_SIP_TRUNK_ID not configured")

    if request.skill_pack_id:
        sp_result = await db.execute(
            select(SkillPackModel).where(SkillPackModel.id == request.skill_pack_id)
        )
        sp_row = sp_result.scalar_one_or_none()
        if sp_row is None:
            raise HTTPException(status_code=404, detail="Skill Pack not found")
        yaml_content = sp_row.yaml_content
    else:
        active_result = await db.execute(
            select(SkillPackModel).where(SkillPackModel.is_active == True)  # noqa: E712
        )
        active_row = active_result.scalar_one_or_none()
        if active_row is None:
            raise HTTPException(status_code=400, detail="No active Skill Pack found")
        yaml_content = active_row.yaml_content

    try:
        parsed = parse_skill_pack_yaml(yaml_content)
    except ParseError as exc:
        raise HTTPException(status_code=422, detail=f"YAML parse error: {exc.message}")

    result = validate_skill_pack(parsed)
    if not result.is_valid:
        raise HTTPException(status_code=422, detail={"message": "Validation failed", "errors": result.errors})

    # Apply overrides
    if request.tts_voice:
        parsed.setdefault("agent", {})["tts_voice"] = request.tts_voice
    if request.llm_model:
        agent = parsed.setdefault("agent", {})
        prefs = agent.setdefault("model_preferences", [{}])
        if prefs:
            prefs[0]["model"] = request.llm_model
    if request.agent_name:
        parsed.setdefault("agent", {})["name"] = request.agent_name
    if request.context_data:
        parsed["context_data"] = request.context_data
    if request.language:
        parsed.setdefault("agent", {})["language"] = request.language

    # Filter sections by selected mode (_mode in context_data)
    if request.context_data and '_mode' in request.context_data:
        selected_mode = request.context_data['_mode']
        all_sections = parsed.get('sections', [])
        filtered = [s for s in all_sections if s.get('mode', '') == selected_mode]
        if filtered:
            parsed['sections'] = filtered

    parsed["channel"] = "phone"

    # Create session
    session_state = await create_phone_session(parsed, request.phone_number, db, context_data=request.context_data)

    # Create LiveKit SIP outbound call
    try:
        # Extract voice from tts_voice (format: sarvam:shubh -> shubh)
        voice = request.tts_voice or "shubh"
        if ":" in voice:
            voice = voice.split(":")[-1]
        
        # Get language from skill pack or default
        language = parsed.get("agent", {}).get("language", "en-IN")
        
        call_sid = await create_sip_outbound_call(
            session_id=session_state.session_id,
            phone_number=request.phone_number,
            skill_pack=parsed,
            sip_trunk_id=sip_trunk_id,
            voice=voice,
            llm_model=request.llm_model or "sarvam-30b",
            language=language,
            agent_name=request.agent_name,
            db=db,
        )
        logger.info("Created LiveKit SIP call %s for session %s", call_sid, session_state.session_id)
    except Exception as exc:
        logger.error("Failed to create LiveKit SIP call: %s", exc)
        raise HTTPException(status_code=503, detail=f"Failed to place call: {exc}")

    return {"session_id": session_state.session_id, "status": "pending"}


# Background bot poller (simplified)
async def _poll_bot_until_active(session_id: str, bot_id: str, skill_pack: dict) -> None:
    """Poll Recall.ai until bot is ready, then start pipeline."""
    from backend.recall_client import get_bot_status
    from backend.session_manager import register_pipeline

    api_key = os.environ.get("RECALL_API_KEY", "")
    logger.info("poll_bot[%s]: starting status poll for bot %s", session_id, bot_id)

    for attempt in range(36):  # 3 minutes max
        await asyncio.sleep(5)
        try:
            status = await get_bot_status(bot_id, api_key)
            logger.info("poll_bot[%s]: bot status=%s (attempt %d)", session_id, status, attempt + 1)
        except Exception as exc:
            logger.warning("poll_bot[%s]: status check failed: %s", session_id, exc)
            continue

        if status == "in_call_recording":
            # Update session status and start pipeline with full callback wiring
            try:
                from backend.db import get_db
                from backend.models import Session as SessionModel
                from sqlalchemy import update as _update
                now = datetime.now(tz=timezone.utc)
                async for db in get_db():
                    await db.execute(
                        _update(SessionModel)
                        .where(SessionModel.session_id == session_id)
                        .values(status="active", started_at=now)
                    )
                    await db.commit()
                    break
            except Exception as exc:
                logger.warning("poll_bot[%s]: session status update failed: %s", session_id, exc)

            try:
                from backend.routers.recall import _create_and_start_pipeline, _claim_pipeline_slot, _session_cache
                claimed = await _claim_pipeline_slot(session_id)
                if not claimed:
                    logger.info("poll_bot[%s]: pipeline slot already claimed — skipping", session_id)
                    return
                await _create_and_start_pipeline(session_id=session_id, skill_pack=skill_pack, bot_id=bot_id)
                _session_cache[bot_id] = session_id
                logger.info("poll_bot[%s]: pipeline started", session_id)
            except Exception as exc:
                logger.error("poll_bot[%s]: pipeline start failed: %s", session_id, exc)
            return

        if status in ("done", "fatal_error", "call_ended"):
            logger.warning("poll_bot[%s]: bot ended with status=%s", session_id, status)
            try:
                from backend.db import get_db
                from backend.models import Session as SessionModel
                from sqlalchemy import select as _select
                from backend.session_manager import get_pipeline, unregister_pipeline, close_session
                async for db in get_db():
                    result = await db.execute(_select(SessionModel).where(SessionModel.session_id == session_id))
                    session_row = result.scalar_one_or_none()
                    if session_row and session_row.status not in ("completed", "failed"):
                        pipeline = await get_pipeline(session_id)
                        if pipeline is not None:
                            try:
                                await pipeline.stop()
                            except Exception:
                                pass
                            await unregister_pipeline(session_id)
                        await close_session(session_id, db)
                    break
            except Exception as exc:
                logger.warning("poll_bot[%s]: close_session failed: %s", session_id, exc)
            return

    logger.error("poll_bot[%s]: gave up after 3 minutes", session_id)


# -----------------------------------------------------------------------------
# Recording endpoints
# -----------------------------------------------------------------------------

class RecordingInfo(BaseModel):
    """Recording info schema."""
    recording_sid: str
    call_sid: str
    duration_sec: int
    status: str
    date_created: str
    uri: str


class RecordingListResponse(BaseModel):
    """Recording list response schema."""
    session_id: str
    twilio_call_sid: Optional[str]
    recordings: list[RecordingInfo]


@router.get("/{session_id}/recordings", response_model=RecordingListResponse)
async def get_session_recordings(
    session_id: str,
    db: AsyncSession = Depends(_get_db),
    token: str = Depends(verify_token),
):
    """Get all Twilio recordings for a session.

    Returns recording metadata including URLs for downloading audio.
    """
    from backend.mcp.twilio_client import get_twilio_mcp_client

    # Get session from DB
    result = await db.execute(
        select(SessionModel).where(SessionModel.session_id == session_id)
    )
    session_row = result.scalar_one_or_none()

    if session_row is None:
        raise HTTPException(status_code=404, detail="Session not found")

    call_sid = session_row.twilio_call_sid
    if not call_sid:
        # Return empty list if no Twilio call associated
        return RecordingListResponse(
            session_id=session_id,
            twilio_call_sid=None,
            recordings=[]
        )

    try:
        client = get_twilio_mcp_client()
        recordings = await client.get_recordings(call_sid)

        return RecordingListResponse(
            session_id=session_id,
            twilio_call_sid=call_sid,
            recordings=[
                RecordingInfo(
                    recording_sid=r["sid"],
                    call_sid=r["call_sid"],
                    duration_sec=int(r.get("duration", 0)),
                    status=r["status"],
                    date_created=r["date_created"],
                    uri=f"/api/sessions/{session_id}/recordings/{r['sid']}/download",
                )
                for r in recordings
            ]
        )
    except Exception as exc:
        logger.error("Failed to get recordings for session %s: %s", session_id, exc)
        raise HTTPException(status_code=503, detail=f"Failed to fetch recordings: {exc}")


@router.get("/{session_id}/recordings/{recording_sid}/download")
async def download_recording(
    session_id: str,
    recording_sid: str,
    token: Optional[str] = Query(None),  # Accept token as query param
    db: AsyncSession = Depends(_get_db),
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security),
):
    """Download a specific recording audio file.
    
    Accepts authentication via either:
    - Authorization: Bearer <token> header
    - ?token=<token> query parameter (for browser audio/download elements)
    
    Proxies the audio through the backend to avoid browser auth prompts
    (Twilio's API requires HTTP Basic Auth which browsers can't handle).
    """
    from backend.mcp.twilio_client import get_twilio_mcp_client
    from fastapi.responses import Response
    import httpx

    # Validate token from either source (header or query param)
    api_token = os.environ.get("API_TOKEN", "")
    bearer_token = credentials.credentials if credentials else None
    auth_token = bearer_token or token
    
    if api_token:  # Only validate if API_TOKEN is configured
        if not auth_token or not _constant_time_compare(auth_token, api_token):
            raise HTTPException(status_code=401, detail="Authentication required")
    elif not auth_token:
        # Dev mode: warn but allow if no API_TOKEN configured
        logger.warning("API_TOKEN not configured - authentication disabled for download")

    # Verify session exists
    result = await db.execute(
        select(SessionModel).where(SessionModel.session_id == session_id)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        client = get_twilio_mcp_client()
        # Get the Twilio media URL
        media_url = await client.get_recording_media_url(recording_sid)
        
        # Fetch from Twilio with server-side credentials (proxy instead of redirect)
        account_sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
        twilio_auth_token = os.environ.get("TWILIO_AUTH_TOKEN", "")
        
        async with httpx.AsyncClient() as http_client:
            twilio_response = await http_client.get(
                media_url,
                auth=(account_sid, twilio_auth_token),
                follow_redirects=True,
                timeout=60.0,  # Recordings can be large
            )
            twilio_response.raise_for_status()
        
        # Determine content type from Twilio's response
        content_type = twilio_response.headers.get("content-type", "audio/mpeg")
        
        return Response(
            content=twilio_response.content,
            media_type=content_type,
            headers={
                "Content-Disposition": f'inline; filename="recording-{recording_sid}.mp3"',
            },
        )
    except httpx.HTTPStatusError as exc:
        logger.error("Twilio returned error for recording %s: %s", recording_sid, exc)
        raise HTTPException(status_code=502, detail=f"Twilio API error: {exc.response.status_code}")
    except Exception as exc:
        logger.error("Failed to get recording %s: %s", recording_sid, exc)
        raise HTTPException(status_code=503, detail=f"Failed to fetch recording: {exc}")


@router.delete("/{session_id}")
async def delete_session_endpoint(
    session_id: str,
    db: AsyncSession = Depends(_get_db),
    token: str = Depends(verify_token),
):
    """Manually terminate a session.

    Sends session_end with reason=manual to the pipeline, then triggers
    the close flow (report generation + status transition).
    """
    from backend.session_manager import (
        SessionStatus,
        close_session,
        get_pipeline,
        unregister_pipeline,
    )

    # Look up session in DB
    result = await db.execute(
        select(SessionModel).where(SessionModel.session_id == session_id)
    )
    session_row = result.scalar_one_or_none()
    if session_row is None:
        raise HTTPException(status_code=404, detail="Session not found")

    # Reject if already closed (allow CLOSING to be idempotent)
    if session_row.status in (SessionStatus.COMPLETED.value, SessionStatus.FAILED.value, "CLOSING"):
        return {"session_id": session_id, "status": session_row.status}

    # Stop the active pipeline (sends session_end with reason=manual internally)
    pipeline = await get_pipeline(session_id)
    if pipeline is not None:
        try:
            await pipeline.stop()
            logger.info("Pipeline stopped for session %s", session_id)
        except Exception as exc:
            logger.warning(
                "Error stopping pipeline for session %s: %s — proceeding with close",
                session_id,
                exc,
            )
        await unregister_pipeline(session_id)
    else:
        logger.warning(
            "No active pipeline found for session %s — proceeding with close_session",
            session_id,
        )

    # Trigger report generation and status transition
    await close_session(session_id, db)

    return {"session_id": session_id, "status": "closing"}


# ---------------------------------------------------------------------------
# GET /sessions/{session_id}/transcript
# ---------------------------------------------------------------------------

class TurnRecord(BaseModel):
    turn_index: int
    speaker: str
    transcript: str
    timestamp_ms: Optional[int]
    question_id: Optional[str]
    score: Optional[int]
    score_rationale: Optional[str]
    competency: Optional[str]
    flags: Optional[list]
    action: Optional[str]


class TranscriptResponse(BaseModel):
    session_id: str
    turns: list[TurnRecord]


@router.get("/{session_id}/transcript", response_model=TranscriptResponse)
async def get_session_transcript(
    session_id: str,
    db: AsyncSession = Depends(_get_db),
):
    """Return all turns for a session ordered by turn_index ascending."""
    # Verify session exists
    session_result = await db.execute(
        select(SessionModel).where(SessionModel.session_id == session_id)
    )
    if session_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Session not found")

    turns_result = await db.execute(
        select(TurnModel)
        .where(TurnModel.session_id == session_id)
        .order_by(TurnModel.turn_index.asc())
    )
    turn_rows = turns_result.scalars().all()

    turns = []
    for turn in turn_rows:
        # Skip turns with blank transcripts (latency-tracking placeholders)
        if not turn.transcript:
            continue
        turns.append({
            "turn_index": turn.turn_index,
            "speaker": turn.speaker,
            "transcript": turn.transcript,
            # eou_ts_ms is used to store the turn timestamp (no separate timestamp_ms column)
            "timestamp_ms": turn.eou_ts_ms,
            "question_id": turn.question_id,
            "score": turn.score,
            "score_rationale": turn.score_rationale,
            "competency": turn.competency,
            "flags": turn.flags,
            "action": turn.action,
        })

    return {"session_id": session_id, "turns": turns}

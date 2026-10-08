"""LiveKit agent callback router."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db import get_db
from backend.models import Session as SessionModel

router = APIRouter(prefix="/livekit", tags=["livekit"])


class LiveKitSessionActiveRequest(BaseModel):
    """Request schema for session active callback."""
    session_id: str


class LiveKitSessionSummaryRequest(BaseModel):
    """Request schema for session summary callback."""
    session_id: str
    summary: dict


class LiveKitTurnRequest(BaseModel):
    """Request schema for turn transcript callback."""
    session_id: str
    turn_index: int
    speaker: str
    transcript: str
    timestamp_ms: int


@router.post("/session-active")
async def livekit_session_active(
    request: LiveKitSessionActiveRequest,
    db: AsyncSession = Depends(get_db),
):
    """Called by the LiveKit agent worker when a session becomes active."""
    now = datetime.now(tz=timezone.utc)
    result = await db.execute(
        select(SessionModel).where(SessionModel.session_id == request.session_id)
    )
    row = result.scalar_one_or_none()
    if row:
        row.status = "active"
        row.started_at = now
        await db.commit()
    return {"ok": True}


@router.post("/turn")
async def livekit_turn(
    request: LiveKitTurnRequest,
    db: AsyncSession = Depends(get_db),
):
    """Called by the LiveKit agent worker when a turn is completed."""
    from backend.session_manager import add_turn_transcript
    await add_turn_transcript(
        session_id=request.session_id,
        turn_index=request.turn_index,
        speaker=request.speaker,
        transcript=request.transcript,
        timestamp_ms=request.timestamp_ms,
        db=db,
    )
    return {"ok": True}


@router.post("/session-summary")
async def livekit_session_summary(
    request: LiveKitSessionSummaryRequest,
    db: AsyncSession = Depends(get_db),
):
    """Called by the LiveKit agent worker with session summary for report generation."""
    from backend.session_manager import close_session, store_session_summary
    await store_session_summary(request.session_id, request.summary)
    await close_session(request.session_id, db)
    return {"ok": True}


class LiveKitSessionCloseRequest(BaseModel):
    """Request schema for session close callback (no summary available)."""
    session_id: str


@router.post("/session-close")
async def livekit_session_close(
    request: LiveKitSessionCloseRequest,
    db: AsyncSession = Depends(get_db),
):
    """Called by the LiveKit agent worker when participant disconnects mid-session (no summary)."""
    from backend.session_manager import close_session
    await close_session(request.session_id, db)
    return {"ok": True}

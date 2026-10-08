"""Backend API entry point — FastAPI app with lifespan (env check + DB init)."""
import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, Form
from fastapi.middleware.cors import CORSMiddleware

# Configure root logger so named loggers (pipeline, rpc_bridge, etc.) are visible
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

REQUIRED_ENV_VARS = [
    'AZURE_TENANT_ID',
    'AZURE_CLIENT_ID',
    'AZURE_CLIENT_SECRET',
    'RECALL_API_KEY',
    'SARVAM_API_KEY',
    'RESEND_API_KEY',
    'TEAMS_BOT_APP_ID',
    'TEAMS_BOT_APP_PASSWORD',
    'DATABASE_URL',
    'API_TOKEN',
    'REDIS_URL',
]


async def _stale_session_cleanup_loop() -> None:
    """Periodically mark sessions that have been stuck in non-terminal states as failed.

    Runs every 5 minutes. A session is considered stale if it has been in
    active/joining/pending/closing state for more than 90 minutes without ending.
    This catches calls where the participant hung up but the agent failed to notify
    the backend (e.g. network error, agent crash, LiveKit not sending disconnect event).
    """
    STALE_THRESHOLD_MINUTES = 90
    CHECK_INTERVAL_SECONDS = 300  # 5 minutes

    while True:
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)
        try:
            from backend.db import get_db
            from backend.models import Session as SessionModel
            from sqlalchemy import update

            cutoff = datetime.now(tz=timezone.utc) - timedelta(minutes=STALE_THRESHOLD_MINUTES)
            async for db in get_db():
                result = await db.execute(
                    update(SessionModel)
                    .where(
                        SessionModel.status.in_(["active", "joining", "pending", "closing"]),
                        SessionModel.created_at < cutoff,
                    )
                    .values(
                        status="failed",
                        error="Session timed out — participant likely disconnected without proper close",
                    )
                )
                if result.rowcount:
                    logger.warning(
                        "stale_cleanup: marked %d session(s) as failed (stuck >%dm)",
                        result.rowcount,
                        STALE_THRESHOLD_MINUTES,
                    )
                await db.commit()
                break
        except Exception as exc:  # noqa: BLE001
            logger.error("stale_cleanup: error during cleanup: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    missing = [var for var in REQUIRED_ENV_VARS if not os.environ.get(var)]
    if missing:
        for var in missing:
            logger.error("Missing required environment variable: %s", var)
        sys.exit(1)

    from backend.db import init_db, get_db
    await init_db()

    # On startup: close any sessions that were active/joining/pending.
    # Their in-memory pipeline state is gone. Sessions with captured turns
    # get a report generated; sessions with no turns are marked failed.
    try:
        from backend.models import Session as SessionModel, Turn as TurnModel
        from backend.session_manager import close_session
        from sqlalchemy import select, update, func
        async for db in get_db():
            stale = await db.execute(
                select(SessionModel)
                .where(SessionModel.status.in_(["active", "joining", "pending"]))
            )
            stale_sessions = stale.scalars().all()
            closed = 0
            failed = 0
            for sess in stale_sessions:
                turn_count_result = await db.execute(
                    select(func.count()).where(TurnModel.session_id == sess.session_id)
                )
                turn_count = turn_count_result.scalar_one()
                if turn_count > 0:
                    # Has turns — generate report and mark completed
                    try:
                        await close_session(sess.session_id, db)
                        closed += 1
                    except Exception as exc2:
                        logger.warning("lifespan: close_session[%s] failed: %s", sess.session_id, exc2)
                        sess.status = "failed"
                        sess.error = "Backend restarted — pipeline state lost"
                        failed += 1
                else:
                    sess.status = "failed"
                    sess.error = "Backend restarted — pipeline state lost"
                    failed += 1
            await db.commit()
            if closed or failed:
                logger.warning(
                    "lifespan: on restart closed %d session(s) with report, marked %d as failed",
                    closed, failed,
                )
            break
    except Exception as exc:  # noqa: BLE001
        logger.error("lifespan: failed to clean up stale sessions: %s", exc)

    # On startup: flush all stale Redis pipeline registrations.
    # In-memory pipeline objects don't survive restarts, so any Redis entries
    # pointing to the old host are dead and will block audio WebSocket resolution.
    try:
        from backend.redis_client import get_redis_client, PIPELINE_KEY_PREFIX
        redis_client = await get_redis_client()
        if redis_client:
            keys = await redis_client.keys(f"{PIPELINE_KEY_PREFIX}*")
            if keys:
                await redis_client.delete(*keys)
                logger.warning("lifespan: flushed %d stale Redis pipeline registration(s)", len(keys))
    except Exception as exc:  # noqa: BLE001
        logger.error("lifespan: failed to flush Redis pipeline registrations: %s", exc)

    # Start background stale-session cleanup task
    cleanup_task = asyncio.create_task(_stale_session_cleanup_loop())

    yield

    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="Vero AI Agent", lifespan=lifespan)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Import and include routers
from backend.routers import (
    health_router,
    skill_packs_router,
    sessions_router,
    recall_router,
    reports_router,
    events_router,
    docs_router,
    livekit_router,
)

app.include_router(health_router)
app.include_router(skill_packs_router)
app.include_router(sessions_router)
app.include_router(reports_router)
app.include_router(events_router)
app.include_router(docs_router)
app.include_router(livekit_router)
app.include_router(recall_router)


# ---------------------------------------------------------------------------
# Twilio LiveKit bridge endpoint - bridges Twilio calls to LiveKit SIP
# These need to be at /twilio/* paths (not under /sessions prefix)
# ---------------------------------------------------------------------------

@app.get("/twilio/livekit-bridge")
@app.post("/twilio/livekit-bridge")
async def twilio_livekit_bridge(session_id: str):
    """Return TwiML that dials the LiveKit SIP URI.

    When the candidate answers the Twilio outbound call, Twilio fetches this
    endpoint and bridges them into the LiveKit room via the inbound SIP trunk.
    """
    from fastapi.responses import Response

    from_number = os.environ.get("TWILIO_PHONE_NUMBER", "")
    # LiveKit SIP URI — found in LiveKit console under Telephony > Dispatch Rules
    livekit_sip_uri = os.environ.get(
        "LIVEKIT_SIP_URI", "sip:48okyliy0sm.sip.livekit.cloud"
    )
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Dial callerId="{from_number}">
    <Sip>sip:{from_number}@{livekit_sip_uri.replace('sip:', '')}</Sip>
  </Dial>
</Response>"""
    return Response(content=twiml, media_type="application/xml")


@app.post("/twilio/recording-callback")
async def twilio_recording_callback(
    RecordingSid: str = Form(""),
    RecordingUrl: str = Form(""),
    RecordingStatus: str = Form(""),
    CallSid: str = Form(""),
    RecordingDuration: str = Form(""),
):
    """Webhook endpoint for Twilio recording status callbacks.

    Called by Twilio when a recording is completed. Saves the recording URL to the session.
    """
    import logging
    logger = logging.getLogger(__name__)
    logger.info(
        "twilio_recording_callback: sid=%s status=%s call=%s duration=%s",
        RecordingSid,
        RecordingStatus,
        CallSid,
        RecordingDuration,
    )

    # Save recording URL to session if CallSid matches
    if RecordingStatus == "completed" and RecordingUrl and CallSid:
        try:
            from backend.db import get_db
            from backend.models import Session as SessionModel
            from sqlalchemy import select, update

            async for db in get_db():
                # Find session by twilio_call_sid
                result = await db.execute(
                    select(SessionModel).where(SessionModel.twilio_call_sid == CallSid)
                )
                session_row = result.scalar_one_or_none()

                if session_row:
                    # Append .mp3 to get the direct audio file URL
                    audio_url = f"{RecordingUrl}.mp3"
                    await db.execute(
                        update(SessionModel)
                        .where(SessionModel.session_id == session_row.session_id)
                        .values(recording_url=audio_url)
                    )
                    await db.commit()
                    logger.info(
                        "twilio_recording_callback: saved recording URL for session %s",
                        session_row.session_id
                    )
                break
        except Exception as exc:
            logger.error("twilio_recording_callback: failed to save recording URL: %s", exc)

    return {"received": True}


# Backward compatibility: _get_db for tests
async def _get_db():
    """Get database session (for backward compatibility with tests)."""
    from backend.db import get_db
    async for db in get_db():
        yield db


# Backward compatibility: re-export from routers
from backend.routers.recall import recall_webhook, RecallWebhookEvent


@app.get("/")
async def root():
    """Root endpoint - API info."""
    return {
        "name": "Vero AI Agent API",
        "version": "1.0.0",
        "docs": "/docs",
    }

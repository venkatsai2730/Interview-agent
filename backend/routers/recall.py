"""Recall.ai webhook and audio router."""
from __future__ import annotations

import hmac
import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from sqlalchemy import select, update

from backend.db import get_db
from backend.models import Session as SessionModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks/recall", tags=["webhooks"])

# In-memory cache for bot_id -> session_id mapping (used by audio WebSocket)
_session_cache: dict[str, str] = {}

# In-memory cache for session_id -> transcript processing state
_transcript_sessions: dict[str, dict] = {}


class RecallWebhookEvent(BaseModel):
    """Recall.ai webhook event payload."""
    bot_id: str
    status: str
    meeting_url: Optional[str] = None


# ---------------------------------------------------------------------------
# Real-Time Transcription Webhook (Recall.ai sends transcripts here)
# ---------------------------------------------------------------------------

@router.post("/transcription")
async def recall_transcription_webhook(request: Request):
    """Handle real-time transcription events from Recall.ai (v1.11 API).

    Recall.ai sends transcript.data events as participants speak.
    We accumulate transcript segments and debounce before sending to the
    Node.js scoring bridge — this prevents fragmented turns and feedback loops.
    """
    import time as _time

    try:
        payload = await request.json()
    except Exception:
        return {"status": "ok"}

    event_type = payload.get("event")
    if event_type != "transcript.data":
        return {"status": "ok"}

    data = payload.get("data", {})
    bot_data = data.get("bot", {})
    bot_id = bot_data.get("id", "")
    transcript_data = data.get("data", {})

    if not transcript_data or not bot_id:
        return {"status": "ok"}

    # Extract the transcript text from words array
    words = transcript_data.get("words", [])
    if not words:
        return {"status": "ok"}

    text = " ".join(w.get("text", "") for w in words).strip()
    participant = transcript_data.get("participant", {})
    speaker = participant.get("name", "Unknown")
    participant_id = participant.get("id")

    if not text:
        return {"status": "ok"}

    # Resolve session from bot_id
    session_id = _session_cache.get(bot_id)
    if not session_id:
        try:
            async for db in get_db():
                result = await db.execute(
                    select(SessionModel).where(SessionModel.recall_bot_id == bot_id)
                )
                row = result.scalar_one_or_none()
                if row:
                    session_id = row.session_id
                    _session_cache[bot_id] = session_id
                break
        except Exception:
            pass

    if not session_id:
        return {"status": "ok"}

    # Initialize session state
    if session_id not in _transcript_sessions:
        _transcript_sessions[session_id] = {
            "turn_index": 0,
            "bot_participant_id": None,
            "last_agent_response_time": 0,
            "pending_segments": [],
            "debounce_task": None,
        }

    state = _transcript_sessions[session_id]

    # --- FIX #1: Filter out bot's own speech ---
    # The bot's participant_id is detected on first agent TTS output.
    # Also filter by checking if this participant_id matches the bot.
    # Heuristic: if participant is_host=False and name matches bot_name, skip it.
    is_bot = participant.get("is_host") is False and participant_id == state.get("bot_participant_id")

    # Also filter by name matching common bot names
    bot_names = {"vero", "interviewer", "neha", "priya", "alex", "ritu", "shubh", "aditya", "rahul", "pooja", "rohan", "simran", "kavya"}
    if speaker and speaker.lower().strip() in bot_names:
        # This is the bot speaking — record its participant_id for future filtering
        if state.get("bot_participant_id") is None and participant_id is not None:
            state["bot_participant_id"] = participant_id
            logger.info("recall_transcription[%s]: identified bot participant_id=%s (name=%s)",
                       session_id, participant_id, speaker)
        return {"status": "ok"}

    if is_bot:
        return {"status": "ok"}

    # --- FIX #2: Cooldown after agent response ---
    # Don't accept new transcripts for 3 seconds after the agent last spoke.
    # This prevents the bot's own TTS from being transcribed and fed back.
    now = _time.time()
    cooldown_seconds = 3.0
    if now - state["last_agent_response_time"] < cooldown_seconds:
        logger.debug("recall_transcription[%s]: in cooldown, skipping: %s", session_id, text[:40])
        return {"status": "ok"}

    # --- FIX #3: Accumulate segments and debounce ---
    # Don't send every fragment immediately. Collect segments for 2 seconds
    # of silence, then send the combined text as one turn.
    state["pending_segments"].append(text)
    logger.info("recall_transcription[%s]: segment from %s: %s (pending: %d)",
               session_id, speaker, text[:60], len(state["pending_segments"]))

    # Cancel previous debounce task and start a new one
    if state.get("debounce_task") is not None:
        state["debounce_task"].cancel()

    import asyncio
    state["debounce_task"] = asyncio.ensure_future(
        _debounce_and_dispatch(session_id, bot_id, 2.5)
    )

    return {"status": "ok"}


async def _correct_transcript(text: str) -> str:
    """Use a fast LLM to correct obvious STT errors in the transcript.

    Common misrecognitions for Indian-accented English technical speech:
    - "psychic clean" → "scikit-learn"
    - "EECS" → "ECS" (Elastic Container Service)
    - "unrolling mean" → "rolling mean"
    - "tensor flow" → "TensorFlow"
    """
    import httpx
    import os

    # Skip correction for very short or simple text
    if len(text.split()) < 3:
        return text

    gcp_project = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
    gcp_location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")

    if not gcp_project:
        return text

    try:
        from google.auth import default as ga_default
        from google.auth.transport.requests import Request as AuthRequest

        credentials, _ = ga_default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        credentials.refresh(AuthRequest())
        token = credentials.token

        url = (
            f"https://{gcp_location}-aiplatform.googleapis.com/v1/projects/{gcp_project}"
            f"/locations/{gcp_location}/publishers/google/models/gemini-2.0-flash:generateContent"
        )

        prompt = (
            "You are a transcript correction assistant. The following text is a speech-to-text transcript "
            "from a technical interview with an Indian-accented English speaker. The STT made errors on "
            "technical terms. Fix ONLY obvious misrecognitions. Do NOT change the meaning, add content, "
            "or rephrase. Just fix misheard technical words.\n\n"
            "Common corrections:\n"
            "- 'psychic clean' → 'scikit-learn'\n"
            "- 'tensor flow' → 'TensorFlow'\n"
            "- 'pie torch' → 'PyTorch'\n"
            "- 'EECS' → 'ECS' (if talking about AWS)\n"
            "- 'langchain' stays as 'LangChain'\n"
            "- 'chrome DB' → 'ChromaDB'\n"
            "- 'pine cone' → 'Pinecone'\n"
            "- 'sage maker' → 'SageMaker'\n"
            "- 'bed rock' → 'Bedrock'\n"
            "- 'hugging face' → 'HuggingFace'\n"
            "- 'docker' stays as 'Docker'\n"
            "- 'kubernetes' stays as 'Kubernetes'\n\n"
            f"Transcript: {text}\n\n"
            "Corrected transcript (output ONLY the corrected text, nothing else):"
        )

        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": 500},
        }

        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                url,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json=payload,
            )
            if response.status_code == 200:
                data = response.json()
                corrected = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                if corrected and len(corrected) > 0:
                    logger.info("transcript_correction: '%s' → '%s'", text[:60], corrected[:60])
                    return corrected
    except Exception as exc:
        logger.debug("transcript_correction failed: %s", exc)

    return text


async def _debounce_and_dispatch(session_id: str, bot_id: str, delay: float):
    """Wait for `delay` seconds of no new segments, then dispatch combined turn."""
    import asyncio
    import time as _time

    await asyncio.sleep(delay)

    state = _transcript_sessions.get(session_id)
    if not state or not state["pending_segments"]:
        return

    # Combine all pending segments into one turn
    full_text = " ".join(state["pending_segments"]).strip()
    state["pending_segments"] = []
    state["debounce_task"] = None

    if not full_text:
        return

    # Drop pure connectivity noise ("hello?", "are you there?", "can you hear me?")
    # These are the candidate checking audio, not answering the question.
    _NOISE_PHRASES = {"hello", "hello?", "hi", "are you there", "can you hear me",
                      "hello are you there", "is anyone there", "testing"}
    if full_text.strip("?! ").lower() in _NOISE_PHRASES:
        logger.info("recall_transcription[%s]: dropped noise phrase: %s", session_id, full_text)
        return

    # Semantic continuation guard — if the text ends with a conjunction or
    # preposition the speaker clearly wasn't done. Re-arm the debounce once.
    _CONTINUATION_WORDS = {
        "and", "or", "but", "nor", "so", "yet", "for", "because", "since",
        "although", "while", "when", "where", "as", "if", "unless", "until",
        "after", "before", "though", "which", "that", "who", "what", "how",
        "in", "on", "at", "by", "with", "about", "from", "to", "of",
        "the", "a", "an", "this", "these",
    }
    last_word = full_text.rstrip(".,?!;: ").split()[-1].lower() if full_text.split() else ""
    if last_word in _CONTINUATION_WORDS:
        logger.info("recall_transcription[%s]: ends with '%s', re-arming debounce for 2.5s",
                    session_id, last_word)
        state["pending_segments"] = [full_text]
        import asyncio as _asyncio
        state["debounce_task"] = _asyncio.ensure_future(
            _debounce_and_dispatch(session_id, bot_id, 2.5)
        )
        return

    # --- LLM Transcript Correction ---
    # Deepgram often mishears technical terms (scikit-learn → psychic clean, ECS → EECS)
    # Use a fast LLM call to fix obvious STT errors before sending to the scoring agent.
    try:
        full_text = await _correct_transcript(full_text)
    except Exception as exc:
        logger.warning("recall_transcription[%s]: transcript correction failed: %s", session_id, exc)
        # Continue with uncorrected text

    logger.info("recall_transcription[%s]: dispatching combined turn: %s", session_id, full_text[:80])

    # Send to Node.js agent
    from backend.session_manager import get_pipeline
    pipeline = await get_pipeline(session_id)
    if pipeline is None:
        logger.warning("recall_transcription[%s]: no pipeline for dispatch", session_id)
        return

    # If the agent is still processing the previous turn, re-queue this segment
    # rather than sending a duplicate turn that would confuse the agent.
    if getattr(pipeline, "_turn_dispatched", False):
        logger.info("recall_transcription[%s]: agent busy, re-queuing segment: %s",
                    session_id, full_text[:60])
        state["pending_segments"] = [full_text]
        import asyncio as _asyncio
        state["debounce_task"] = _asyncio.ensure_future(
            _debounce_and_dispatch(session_id, bot_id, 2.5)
        )
        return

    try:
        from pipeline.rpc_bridge import TurnMessage, serialize_rpc_message

        turn_idx = state["turn_index"]
        state["turn_index"] = turn_idx + 1

        msg = TurnMessage(
            session_id=session_id,
            speaker="participant",
            transcript=full_text,
            turn_index=turn_idx,
            timestamp_ms=int(_time.time() * 1000),
        )

        if pipeline._pi_stdin is not None:
            line = serialize_rpc_message(msg)
            pipeline._pi_stdin.write(line.encode())
            await pipeline._pi_stdin.drain()
            logger.info("recall_transcription[%s]: sent turn %d: %s", session_id, turn_idx, full_text[:60])

            # Lock pipeline so no second fragment interrupts while agent is thinking.
            # Unlocked in pipeline._handle_turn_output once agent responds.
            pipeline._turn_dispatched = True

            # Persist to DB
            if pipeline._on_turn is not None:
                import asyncio as _asyncio
                _asyncio.ensure_future(pipeline._on_turn(
                    session_id, pipeline._db_turn_index, "participant", full_text,
                    int(_time.time() * 1000), None, None, None, None, None, None,
                ))
                pipeline._db_turn_index += 1

            # Mark that we expect an agent response soon — start cooldown when TTS fires
            state["last_agent_response_time"] = _time.time() + 5  # Expect response in ~5s
        else:
            logger.warning("recall_transcription[%s]: pi_agent stdin not available", session_id)
    except Exception as exc:
        logger.error("recall_transcription[%s]: dispatch failed: %s", session_id, exc)


# ---------------------------------------------------------------------------
# Pipeline Factory (avoids direct pipeline import in router)
# ---------------------------------------------------------------------------

async def _create_and_start_pipeline(
    session_id: str,
    skill_pack: dict,
    bot_id: str,
) -> Any:
    """Factory function to create and start a pipeline."""
    from pipeline.pipeline import AudioPipeline
    from backend.session_manager import (
        register_pipeline,
        store_session_summary,
        add_turn_transcript,
        add_turn_latency,
    )

    skill_pack_with_bot = {**skill_pack, "_recall_bot_id": bot_id}

    async def _on_turn(
        sid: str, turn_index: int, speaker: str, transcript: str, timestamp_ms: int,
        question_id, score, score_rationale, competency, flags, action,
    ) -> None:
        async for db in get_db():
            from backend.models import Turn as TurnModel
            from sqlalchemy import select as _select
            result = await db.execute(
                _select(TurnModel).where(
                    TurnModel.session_id == sid,
                    TurnModel.turn_index == turn_index,
                )
            )
            existing = result.scalar_one_or_none()
            if existing:
                existing.speaker = speaker
                existing.transcript = transcript
            else:
                db.add(TurnModel(
                    session_id=sid,
                    turn_index=turn_index,
                    speaker=speaker,
                    transcript=transcript,
                    eou_ts_ms=timestamp_ms,
                    question_id=question_id,
                    score=score,
                    score_rationale=score_rationale,
                    competency=competency,
                    flags=flags,
                    action=action,
                ))
            try:
                await db.commit()
            except Exception as exc:
                await db.rollback()
                logger.warning("_on_turn[%s]: DB commit failed: %s", sid, exc)
            break

    async def _on_latency(sid: str, turn_index: int, eou_ms: int, first_audio_ms: int) -> None:
        async for db in get_db():
            await add_turn_latency(sid, turn_index, eou_ms, first_audio_ms, db)
            break

    # Extract llm_model from skill_pack so the pipeline can select the right STT provider
    llm_model = (skill_pack.get("agent", {})
                 .get("model_preferences", [{}])[0]
                 .get("model", "sarvam-30b"))

    pipeline = AudioPipeline(
        session_id=session_id,
        skill_pack=skill_pack_with_bot,
        on_audio_inject=lambda chunk: None,
        on_session_summary=store_session_summary,
        on_turn=_on_turn,
        on_latency_recorded=_on_latency,
        llm_model=llm_model,
    )
    await pipeline.start()
    await register_pipeline(session_id, pipeline, skill_pack_with_bot)
    return pipeline


async def _claim_pipeline_slot(session_id: str) -> bool:
    """Atomically claim the pipeline slot for a session using a DB-level flag.

    Sets pipeline_started_at to now() only if it is currently NULL.
    Returns True if this process won the race, False if another process
    (or a previous run) already claimed it.
    """
    now = datetime.now(tz=timezone.utc)
    try:
        async for db in get_db():
            # Only update if pipeline_started_at IS NULL — atomic guard
            result = await db.execute(
                update(SessionModel)
                .where(
                    SessionModel.session_id == session_id,
                    SessionModel.pipeline_started_at.is_(None),
                )
                .values(pipeline_started_at=now)
            )
            await db.commit()
            claimed = result.rowcount == 1
            if not claimed:
                logger.warning(
                    "_claim_pipeline_slot[%s]: pipeline already claimed by another process — skipping",
                    session_id,
                )
            return claimed
    except Exception as exc:  # noqa: BLE001
        logger.error("_claim_pipeline_slot[%s]: DB error: %s", session_id, exc)
        return False
    return False


def _verify_recall_signature(request_body: bytes, signature: Optional[str]) -> bool:
    """Verify Recall.ai webhook signature.

    Recall.ai sends a X-Recall-Signature header with HMAC-SHA256 of the payload.
    """
    if not signature:
        logger.warning("recall_webhook: missing X-Recall-Signature header")
        return False

    webhook_secret = os.environ.get("RECALL_WEBHOOK_SECRET")
    if not webhook_secret:
        # If no secret configured, skip verification (dev mode warning)
        logger.warning("RECALL_WEBHOOK_SECRET not configured — skipping signature verification")
        return True

    expected = hmac.new(
        webhook_secret.encode(),
        request_body,
        hashlib.sha256,
    ).hexdigest()

    # Recall signatures may be prefixed with "sha256="
    if signature.startswith("sha256="):
        signature = signature[7:]

    return hmac.compare_digest(expected, signature)


@router.post("/")
async def recall_webhook(request: Request):
    """Handle Recall.ai bot status webhooks.

    Triggers pipeline activation when bot reaches in_call_recording state.
    Captures recording URL when recording is complete.
    Includes signature verification and atomic pipeline slot claiming.
    """
    # Read raw body for signature verification
    body = await request.body()

    # Verify webhook signature (Issue #3 fix)
    signature = request.headers.get("X-Recall-Signature")
    if not _verify_recall_signature(body, signature):
        logger.warning("recall_webhook: signature verification failed")
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload = await request.json()
    except Exception as exc:
        logger.error("recall_webhook: failed to parse JSON: %s", exc)
        raise HTTPException(status_code=400, detail="Invalid JSON")

    bot_id = payload.get("bot_id")
    status = payload.get("status")
    recording_url = payload.get("recording_url")

    if not bot_id or not status:
        logger.warning("recall_webhook: missing bot_id or status")
        raise HTTPException(status_code=400, detail="Missing bot_id or status")

    logger.info("recall_webhook: bot_id=%s status=%s", bot_id, status)

    # Handle call-ended statuses — close session and generate report
    if status in ("done", "call_ended", "fatal_error", "error"):
        async for db in get_db():
            result = await db.execute(
                select(SessionModel).where(SessionModel.recall_bot_id == bot_id)
            )
            session_row = result.scalar_one_or_none()
            if session_row and session_row.status not in ("completed", "failed"):
                logger.info(
                    "recall_webhook: bot %s reached terminal status=%s — closing session %s",
                    bot_id, status, session_row.session_id,
                )
                # Stop the pipeline if running
                from backend.session_manager import get_pipeline, unregister_pipeline
                pipeline = await get_pipeline(session_row.session_id)
                if pipeline is not None:
                    try:
                        await pipeline.stop()
                    except Exception as exc:
                        logger.warning("recall_webhook: pipeline.stop() failed: %s", exc)
                    await unregister_pipeline(session_row.session_id)

                from backend.session_manager import close_session
                await close_session(session_row.session_id, db)
            break
        return {"status": "ok"}

    # Handle recording completion
    if status == "recording_complete" and recording_url:
        async for db in get_db():
            result = await db.execute(
                select(SessionModel).where(SessionModel.recall_bot_id == bot_id)
            )
            session_row = result.scalar_one_or_none()

            if session_row:
                session_row.recall_recording_url = recording_url
                await db.commit()
                logger.info("recall_webhook: saved recording URL for session %s", session_row.session_id)
            break
        return {"status": "ok"}

    if status == "in_call_recording":
        # Find session by bot_id
        async for db in get_db():
            result = await db.execute(
                select(SessionModel).where(SessionModel.recall_bot_id == bot_id)
            )
            session_row = result.scalar_one_or_none()

            if session_row is None:
                logger.warning("recall_webhook: no session found for bot_id=%s", bot_id)
                raise HTTPException(status_code=404, detail="Session not found")

            # Update session status
            if session_row.status != "active":
                session_row.status = "active"
                session_row.started_at = datetime.now(tz=timezone.utc)
                await db.commit()
                logger.info("recall_webhook: session %s activated", session_row.session_id)

            # Atomic pipeline slot claiming (Issue #1 fix)
            # Prevents duplicate starts from webhook + poller race conditions
            claimed = await _claim_pipeline_slot(session_row.session_id)
            if not claimed:
                logger.info(
                    "recall_webhook[%s]: pipeline slot already claimed — skipping duplicate start",
                    session_row.session_id,
                )
                return {"status": "ok", "message": "Pipeline already started"}

            # Start pipeline via factory (Issue #1 fix)
            # Avoids direct pipeline import in router layer
            try:
                await _create_and_start_pipeline(
                    session_id=session_row.session_id,
                    skill_pack=session_row.skill_pack or {},
                    bot_id=bot_id,
                )
                logger.info(
                    "recall_webhook: pipeline started for session %s",
                    session_row.session_id,
                )
            except Exception as exc:
                logger.error("recall_webhook: pipeline start failed: %s", exc)
                raise HTTPException(status_code=500, detail="Pipeline start failed")

            # Cache the bot_id -> session_id mapping for audio WebSocket
            _session_cache[bot_id] = session_row.session_id

            break

    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Recall.ai realtime audio WebSocket — receives audio_mixed_raw.data frames
# ---------------------------------------------------------------------------

@router.websocket("/audio")
async def recall_audio_ws(websocket: WebSocket):
    """WebSocket endpoint that Recall.ai connects to for audio streaming.

    Recall.ai sends JSON frames with event=audio_mixed_raw.data containing
    base64-encoded 16kHz mono S16LE PCM. Bot ID is extracted from the first frame.
    """
    import base64

    await websocket.accept()
    logger.info("recall_audio_ws: Recall.ai connected")

    bot_id: Optional[str] = None
    session_id: Optional[str] = None
    pipeline = None
    _pipeline_resolve_attempts: int = 0
    _pipeline_resolve_max: int = 60  # try for up to ~30s (every other frame)

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except Exception:
                continue

            event = msg.get("event")
            if event != "audio_mixed_raw.data":
                continue

            # Extract bot_id from first frame
            if bot_id is None:
                bot_id = msg.get("data", {}).get("bot", {}).get("id")
                if not bot_id:
                    continue
                logger.info("recall_audio_ws: got bot_id=%s from first frame", bot_id)

            # Resolve session and pipeline — try in-memory cache first, then DB
            if pipeline is None:
                _pipeline_resolve_attempts += 1

                # In-memory cache hit
                if bot_id in _session_cache:
                    session_id = _session_cache[bot_id]
                else:
                    # DB fallback — Recall.ai audio WS often arrives before
                    # the webhook or poller has populated _session_cache
                    try:
                        async for db in get_db():
                            result = await db.execute(
                                select(SessionModel).where(SessionModel.recall_bot_id == bot_id)
                            )
                            row = result.scalar_one_or_none()
                            if row:
                                session_id = row.session_id
                                _session_cache[bot_id] = session_id
                                logger.info(
                                    "recall_audio_ws: resolved session %s from DB for bot %s",
                                    session_id, bot_id,
                                )
                            break
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("recall_audio_ws: DB lookup failed: %s", exc)

                if session_id:
                    from backend.session_manager import get_pipeline
                    pipeline = await get_pipeline(session_id)

                if pipeline is None and session_id:
                    # Pipeline not ready — start it directly from here instead of waiting
                    # This fixes the race condition where audio arrives before the poller starts the pipeline
                    if _pipeline_resolve_attempts == 1:
                        logger.info(
                            "recall_audio_ws[%s]: pipeline not ready, starting it now for session %s",
                            bot_id, session_id,
                        )
                        try:
                            # Get skill_pack from session DB row
                            async for db in get_db():
                                result = await db.execute(
                                    select(SessionModel).where(SessionModel.session_id == session_id)
                                )
                                row = result.scalar_one_or_none()
                                if row and row.skill_pack:
                                    claimed = await _claim_pipeline_slot(session_id)
                                    if claimed:
                                        pipeline = await _create_and_start_pipeline(
                                            session_id=session_id,
                                            skill_pack=row.skill_pack,
                                            bot_id=bot_id,
                                        )
                                        # Update session status to active
                                        from sqlalchemy import update as _update
                                        now = datetime.now(tz=timezone.utc)
                                        await db.execute(
                                            _update(SessionModel)
                                            .where(SessionModel.session_id == session_id)
                                            .values(status="active", started_at=now)
                                        )
                                        await db.commit()
                                        logger.info(
                                            "recall_audio_ws[%s]: pipeline started from WebSocket handler",
                                            bot_id,
                                        )
                                break
                        except Exception as exc:
                            logger.warning("recall_audio_ws[%s]: failed to start pipeline: %s", bot_id, exc)
                    
                    if pipeline is None:
                        # Still waiting — try to get it (poller may have started it)
                        pipeline = await get_pipeline(session_id) if session_id else None

                if pipeline is None:
                    if _pipeline_resolve_attempts % 10 == 0:
                        logger.warning(
                            "recall_audio_ws[%s]: pipeline not ready yet (attempt %d) — dropping frames",
                            bot_id, _pipeline_resolve_attempts,
                        )
                    if _pipeline_resolve_attempts >= _pipeline_resolve_max:
                        logger.error(
                            "recall_audio_ws[%s]: pipeline never became ready after %d attempts — closing",
                            bot_id, _pipeline_resolve_attempts,
                        )
                        break
                    continue

                logger.info("recall_audio_ws[%s]: pipeline resolved for session %s", bot_id, session_id)

            b64 = msg.get("data", {}).get("data", {}).get("buffer", "")
            if not b64:
                continue

            try:
                pcm_bytes = base64.b64decode(b64)
                pipeline.process_audio_frame(pcm_bytes)
            except Exception as exc:  # noqa: BLE001
                logger.warning("recall_audio_ws[%s]: frame error: %s", bot_id, exc)

    except WebSocketDisconnect:
        logger.info("recall_audio_ws[%s]: Recall.ai disconnected", bot_id)
    except Exception as exc:  # noqa: BLE001
        logger.error("recall_audio_ws[%s]: error: %s", bot_id, exc)

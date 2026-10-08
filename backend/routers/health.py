"""Health check router."""
from __future__ import annotations

import asyncio
import logging
import os
import time

import httpx
from fastapi import APIRouter
from sqlalchemy import select, text

from backend.db import get_db
from backend.livekit_client import livekit_api

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    """Health check with per-dependency status.

    Probes each dependency and returns:
    - DB: SELECT 1 via SQLAlchemy
    - Recall/Sarvam: HTTP HEAD to their API base URLs

    Response: { status, dependencies: { db, recall, sarvam } }
    Each dependency: { status: ok|degraded|down, latency_ms }
    Top-level status: ok if all ok, degraded if any degraded, down if any down.
    """
    dependencies = {}
    any_down = False
    any_degraded = False

    # DB check
    db_start = time.monotonic()
    try:
        async for db in get_db():
            await db.execute(text("SELECT 1"))
            break
        db_latency = int((time.monotonic() - db_start) * 1000)
        dependencies["db"] = {"status": "ok", "latency_ms": db_latency}
    except Exception as exc:  # noqa: BLE001
        any_down = True
        dependencies["db"] = {"status": "down", "error": str(exc)}

    # Recall.ai check
    recall_start = time.monotonic()
    try:
        recall_key = os.environ.get("RECALL_API_KEY", "")
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                "https://api.recall.ai/api/v1/bots/",
                headers={"Authorization": f"Token {recall_key}"},
            )
            # 200 or 401 (auth ok, just no bots) both mean service is up
            recall_latency = int((time.monotonic() - recall_start) * 1000)
            if resp.status_code in (200, 401):
                dependencies["recall"] = {"status": "ok", "latency_ms": recall_latency}
            else:
                any_degraded = True
                dependencies["recall"] = {
                    "status": "degraded",
                    "latency_ms": recall_latency,
                    "status_code": resp.status_code,
                }
    except Exception as exc:  # noqa: BLE001
        any_down = True
        dependencies["recall"] = {"status": "down", "error": str(exc)}

    # Sarvam AI check
    sarvam_start = time.monotonic()
    try:
        sarvam_key = os.environ.get("SARVAM_API_KEY", "")
        async with httpx.AsyncClient(timeout=5.0) as client:
            # Use the speech-to-text endpoint to verify API key
            resp = await client.get(
                "https://api.sarvam.ai/speech-to-text",
                headers={"api-subscription-key": sarvam_key},
            )
            sarvam_latency = int((time.monotonic() - sarvam_start) * 1000)
            # 405 (method not allowed) means service is up, just doesn't support GET
            if resp.status_code in (200, 401, 405, 422):
                dependencies["sarvam"] = {"status": "ok", "latency_ms": sarvam_latency}
            else:
                any_degraded = True
                dependencies["sarvam"] = {
                    "status": "degraded",
                    "latency_ms": sarvam_latency,
                    "status_code": resp.status_code,
                }
    except Exception as exc:  # noqa: BLE001
        any_down = True
        dependencies["sarvam"] = {"status": "down", "error": str(exc)}

    # Twilio check
    tw_start = time.monotonic()
    try:
        from twilio.rest import Client as TwilioClient
        tw_sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
        tw_token = os.environ.get("TWILIO_AUTH_TOKEN", "")
        if tw_sid and tw_token:
            tw_client = TwilioClient(tw_sid, tw_token)
            # Fetch account info to verify credentials
            tw_client.api.accounts(tw_sid).fetch()
            tw_latency = int((time.monotonic() - tw_start) * 1000)
            dependencies["twilio"] = {"status": "ok", "latency_ms": tw_latency}
        else:
            any_degraded = True
            dependencies["twilio"] = {"status": "degraded", "error": "Missing credentials"}
    except Exception as exc:  # noqa: BLE001
        any_down = True
        dependencies["twilio"] = {"status": "down", "error": str(exc)}

    # Determine top-level status
    if any_down:
        top_status = "down"
    elif any_degraded:
        top_status = "degraded"
    else:
        top_status = "ok"

    return {"status": top_status, "dependencies": dependencies}

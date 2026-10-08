"""Recall.ai REST API client — bot creation and audio output."""
from __future__ import annotations

import asyncio
import base64
import logging
import os

import httpx

# Minimal silent MP3 frame — required to enable the output_audio endpoint
_SILENT_MP3_B64 = (
    "//uQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
)

logger = logging.getLogger(__name__)


class RecallJoinError(Exception):
    """Raised when the Recall.ai bot fails to join after one retry."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class InvalidMeetingUrlError(Exception):
    """Raised when Recall.ai returns a 4xx response (invalid/expired meeting URL)."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


async def acquire_teams_token() -> str:
    """Acquire an Azure AD OAuth 2.0 access token using client credentials flow.

    Reads AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET from the
    environment and POSTs to the Microsoft identity platform token endpoint.

    Returns:
        The access_token string.

    Raises:
        RuntimeError: If required env vars are missing or the token request fails.
    """
    tenant_id = os.environ.get("AZURE_TENANT_ID")
    client_id = os.environ.get("AZURE_CLIENT_ID")
    client_secret = os.environ.get("AZURE_CLIENT_SECRET")

    missing = [
        name
        for name, val in [
            ("AZURE_TENANT_ID", tenant_id),
            ("AZURE_CLIENT_ID", client_id),
            ("AZURE_CLIENT_SECRET", client_secret),
        ]
        if not val
    ]
    if missing:
        raise RuntimeError(
            f"Missing required Azure AD environment variables: {', '.join(missing)}"
        )

    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    data = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "https://graph.microsoft.com/.default",
    }

    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            response = await client.post(token_url, data=data)
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise RuntimeError(
                "Azure AD token request timed out after 5 seconds"
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"Azure AD token request failed with status {exc.response.status_code}: "
                f"{exc.response.text}"
            ) from exc

    token_data = response.json()
    access_token = token_data.get("access_token")
    if not access_token:
        raise RuntimeError(
            f"Azure AD token response did not contain access_token: {token_data}"
        )

    return access_token


async def create_bot(meeting_url: str, bot_name: str, api_key: str) -> str:
    """Create a Recall.ai bot for the given meeting URL.

    Acquires an Azure AD token and passes it to Recall.ai so the bot joins
    as an authenticated Teams participant.

    Implements one retry after a 10-second timeout or 5xx response.
    Raises InvalidMeetingUrlError immediately on 4xx (no retry).
    Raises RecallJoinError if the retry also fails.

    Returns:
        The bot_id string from the Recall.ai response.
    """
    url = f"https://{os.environ.get('RECALL_REGION', 'us-east-1')}.recall.ai/api/v1/bot/"
    headers = {"Authorization": f"Token {api_key}"}

    # Acquire Azure AD token for authenticated Teams join
    azure_token = await acquire_teams_token()

    webhook_url = os.environ.get("WEBHOOK_URL", "")

    payload = {
        "meeting_url": meeting_url,
        "bot_name": bot_name,
        "teams_auth_token": azure_token,
        # Required to enable the output_audio endpoint for TTS injection
        "automatic_audio_output": {
            "in_call_recording": {
                "data": {
                    "kind": "mp3",
                    "b64_data": _SILENT_MP3_B64,
                }
            }
        },
        "recording_config": {
            "transcript": {
                "provider": {
                    "deepgram_streaming": {
                        "language": "en-IN",
                        "model": "nova-3",
                    }
                },
                "diarization": {
                    "use_separate_streams_when_available": True,
                },
            },
            "realtime_endpoints": [
                {
                    "type": "webhook",
                    "url": f"{webhook_url}/webhooks/recall/transcription",
                    "events": ["transcript.data"],
                }
            ] if webhook_url else [],
        },
    }

    async def _attempt() -> str:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            # 4xx → invalid/expired meeting URL — raise immediately, no retry
            if 400 <= response.status_code < 500:
                raise InvalidMeetingUrlError(
                    f"Recall.ai rejected the meeting URL (HTTP {response.status_code}): "
                    f"{response.text}"
                )
            response.raise_for_status()
            data = response.json()
            return data["id"]

    # First attempt
    try:
        return await _attempt()
    except InvalidMeetingUrlError:
        # Propagate immediately — no retry for client errors
        raise
    except (httpx.TimeoutException, httpx.HTTPStatusError) as first_exc:
        first_msg = str(first_exc)
        logger.warning(
            "Recall.ai bot creation failed (attempt 1): %s — retrying in 10s", first_msg
        )

    await asyncio.sleep(10)

    # Retry (only reached for timeouts / 5xx)
    try:
        return await _attempt()
    except InvalidMeetingUrlError:
        raise
    except (httpx.TimeoutException, httpx.HTTPStatusError) as retry_exc:
        raise RecallJoinError(str(retry_exc)) from retry_exc


async def get_bot_status(bot_id: str, api_key: str) -> str:
    """Return the latest status code for a bot (e.g. 'in_call_recording', 'done')."""
    region = os.environ.get("RECALL_REGION", "us-east-1")
    url = f"https://{region}.recall.ai/api/v1/bot/{bot_id}/"
    headers = {"Authorization": f"Token {api_key}"}
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    status_changes = data.get("status_changes", [])
    if status_changes:
        return status_changes[-1].get("code", "unknown")
    return "unknown"


async def output_audio_mp3(bot_id: str, mp3_bytes: bytes, api_key: str) -> None:
    """Inject MP3 audio into the meeting via the Recall.ai output_audio endpoint.

    Args:
        bot_id: The Recall.ai bot ID.
        mp3_bytes: Raw MP3 audio bytes to inject.
        api_key: Recall.ai API key.
    """
    region = os.environ.get("RECALL_REGION", "us-east-1")
    url = f"https://{region}.recall.ai/api/v1/bot/{bot_id}/output_audio/"
    headers = {"Authorization": f"Token {api_key}", "Content-Type": "application/json"}
    b64_data = base64.b64encode(mp3_bytes).decode()
    payload = {"kind": "mp3", "b64_data": b64_data}

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code >= 400:
            logger.warning(
                "output_audio[%s]: Recall.ai returned %d: %s",
                bot_id, resp.status_code, resp.text[:200],
            )
        else:
            logger.info("output_audio[%s]: injected %d bytes of MP3", bot_id, len(mp3_bytes))

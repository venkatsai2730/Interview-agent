"""TTS Injector — Sarvam Bulbul v3.

Synthesises an utterance as WAV via Sarvam text-to-speech API and injects it into
the meeting via Recall.ai's output_audio endpoint or phone channel.
"""
from __future__ import annotations

import asyncio
import base64
import io
import logging
import os
import struct
import time
from typing import Callable, Optional

import httpx

logger = logging.getLogger(__name__)

# Sarvam Bulbul v3 TTS endpoint
SARVAM_TTS_URL = "https://api.sarvam.ai/text-to-speech"


class TTSInjector:
    """Synthesise utterances and inject audio into a Recall.ai meeting or phone channel."""

    def __init__(
        self,
        session_id: str,
        on_audio_chunk: Callable[[bytes], None],
        on_vero_speaking: Callable[[bool], None],
        on_first_chunk_ready: Optional[Callable[[int], None]] = None,
        sarvam_api_key: Optional[str] = None,
        recall_bot_id: Optional[str] = None,
        recall_api_key: Optional[str] = None,
        language: str = "en-IN",
    ) -> None:
        self.session_id = session_id
        self._on_audio_chunk = on_audio_chunk
        self._on_vero_speaking = on_vero_speaking
        self._on_first_chunk_ready = on_first_chunk_ready
        self._sarvam_key = sarvam_api_key or os.environ.get("SARVAM_API_KEY", "")
        self._recall_bot_id = recall_bot_id
        self._recall_api_key = recall_api_key or os.environ.get("RECALL_API_KEY", "")
        self._language = language

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def synthesise_and_inject(self, utterance: str, voice_id: str) -> None:
        """Synthesise *utterance* via Sarvam Bulbul v3 and inject into Recall.ai or phone channel.

        Holds vero_speaking=True for the full audio playback duration so that
        EOU is suppressed and the next TTS cannot start until playback completes.

        Args:
            utterance: The text to synthesise.
            voice_id: Voice identifier in format "sarvam:shubh" or just "shubh".
        """
        self._on_vero_speaking(True)
        try:
            audio_bytes = await self._fetch_sarvam_tts(utterance, voice_id)
            ts_ms = int(time.monotonic() * 1000)
            if self._on_first_chunk_ready:
                self._on_first_chunk_ready(ts_ms)
            logger.info("tts[%s]: Sarvam returned %d bytes", self.session_id, len(audio_bytes))
            duration_s = _wav_duration_seconds(audio_bytes)
            await self._inject(audio_bytes)
            # Hold vero_speaking for the full playback duration so the next TTS
            # doesn't start (and overlap) while this audio is still playing.
            if duration_s > 0.5:
                logger.info("tts[%s]: holding vero_speaking for %.1fs playback", self.session_id, duration_s)
                await asyncio.sleep(duration_s)
        except Exception as exc:
            logger.error("tts[%s]: Sarvam TTS failed: %s", self.session_id, exc)
            raise
        finally:
            self._on_vero_speaking(False)

    async def _inject(self, audio_bytes: bytes) -> None:
        """Route audio to the right channel — Recall.ai or phone (on_audio_chunk callback)."""
        if self._recall_bot_id:
            await self._inject_to_recall(audio_bytes)
        else:
            # Phone channel: send WAV bytes directly via callback
            # The phone channel expects PCM, so we need to convert
            try:
                pcm = _wav_to_pcm16k(audio_bytes)
                self._on_audio_chunk(pcm)
            except Exception as exc:
                logger.error("tts[%s]: phone audio inject failed: %s", self.session_id, exc)

    # ------------------------------------------------------------------
    # Sarvam Bulbul v3 TTS
    # ------------------------------------------------------------------

    async def _fetch_sarvam_tts(self, utterance: str, voice_id: str) -> bytes:
        """Call Sarvam text-to-speech API and return WAV audio bytes.

        Args:
            utterance: The text to synthesise (max 2500 chars for bulbul:v3).
            voice_id: Speaker name like "shubh", "ritu", "aditya", etc.

        Returns:
            WAV audio bytes.
        """
        # Extract speaker name from voice_id (handle "sarvam:shubh" format)
        speaker = voice_id.split(":", 1)[-1] if ":" in voice_id else voice_id

        payload = {
            "text": utterance,
            "target_language_code": self._language,
            "speaker": speaker,
            "model": "bulbul:v3",
            "speech_sample_rate": 16000,  # Match pipeline sample rate
        }
        headers = {
            "api-subscription-key": self._sarvam_key,
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(SARVAM_TTS_URL, json=payload, headers=headers)
                if resp.status_code >= 400:
                    raise _TTSError(f"Sarvam TTS HTTP {resp.status_code}: {resp.text[:500]}")

                data = resp.json()
                # Response contains base64-encoded WAV in 'audios' array
                audios = data.get("audios", [])
                if not audios:
                    raise _TTSError("No audio returned from Sarvam TTS")

                # Decode base64 to WAV bytes
                wav_bytes = base64.b64decode(audios[0])
                return wav_bytes

        except httpx.TimeoutException as exc:
            raise _TTSError(f"Sarvam TTS timeout: {exc}") from exc
        except httpx.HTTPError as exc:
            raise _TTSError(f"Sarvam TTS HTTP error: {exc}") from exc

    # ------------------------------------------------------------------
    # Recall.ai injection
    # ------------------------------------------------------------------

    async def _inject_to_recall(self, audio_bytes: bytes) -> None:
        """POST audio bytes to Recall.ai output_audio endpoint.

        Note: Recall.ai expects MP3, so we need to convert WAV to MP3.
        """
        from backend.recall_client import output_audio_mp3
        try:
            # Convert WAV to MP3 for Recall.ai
            mp3_bytes = _wav_to_mp3(audio_bytes)
            await output_audio_mp3(self._recall_bot_id, mp3_bytes, self._recall_api_key)
        except Exception as exc:
            logger.error("tts[%s]: Recall.ai audio injection failed: %s", self.session_id, exc)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _wav_duration_seconds(wav_bytes: bytes) -> float:
    """Return audio duration in seconds from a WAV header.

    WAV layout (little-endian):
      offset 22: num_channels (uint16)
      offset 24: sample_rate  (uint32)
      offset 34: bits_per_sample (uint16)
      offset 40: data chunk size (uint32)
    """
    try:
        if len(wav_bytes) < 44:
            return 0.0
        num_channels    = struct.unpack_from('<H', wav_bytes, 22)[0]
        sample_rate     = struct.unpack_from('<I', wav_bytes, 24)[0]
        bits_per_sample = struct.unpack_from('<H', wav_bytes, 34)[0]
        data_size       = struct.unpack_from('<I', wav_bytes, 40)[0]
        bytes_per_sample = max(1, bits_per_sample // 8)
        return data_size / max(1, sample_rate * num_channels * bytes_per_sample)
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# Internal exceptions
# ---------------------------------------------------------------------------

class _TTSError(Exception):
    """Raised when TTS synthesis fails."""


# ---------------------------------------------------------------------------
# Audio conversion helpers
# ---------------------------------------------------------------------------

def _wav_to_pcm16k(wav_bytes: bytes) -> bytes:
    """Convert WAV bytes to 16kHz mono signed-16 PCM.

    Sarvam returns WAV at the requested sample rate (16kHz),
    so we just need to extract the raw PCM data after the header.
    """
    try:
        from pydub import AudioSegment
        seg = AudioSegment.from_wav(io.BytesIO(wav_bytes))
        seg = seg.set_frame_rate(16000).set_channels(1).set_sample_width(2)
        return seg.raw_data
    except Exception as exc:
        raise RuntimeError(f"WAV to PCM conversion failed: {exc}") from exc


def _wav_to_mp3(wav_bytes: bytes) -> bytes:
    """Convert WAV bytes to MP3 format for Recall.ai."""
    try:
        from pydub import AudioSegment
        seg = AudioSegment.from_wav(io.BytesIO(wav_bytes))
        mp3_buffer = io.BytesIO()
        seg.export(mp3_buffer, format="mp3")
        return mp3_buffer.getvalue()
    except Exception as exc:
        raise RuntimeError(f"WAV to MP3 conversion failed: {exc}") from exc

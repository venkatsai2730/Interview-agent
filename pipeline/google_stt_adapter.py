"""Google Cloud Speech-to-Text streaming adapter for the Teams audio pipeline.

Provides the same interface as SarvamStreamingSTT so it can be used as a
drop-in replacement in AudioPipeline.

Uses Google Cloud Speech v2 (Chirp) via the google-cloud-speech library
with Application Default Credentials (gcloud auth).
"""
from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class StreamingTranscript:
    text: str
    is_final: bool
    language_code: Optional[str] = None


class GoogleStreamingSTTAdapter:
    """Adapter that wraps Google Cloud Speech-to-Text for the Teams pipeline.
    
    Uses batch recognition (not true streaming) because the Teams pipeline
    buffers audio and sends it in chunks via flush_buffer().
    """

    def __init__(
        self,
        project: str,
        location: str = "global",
        language_code: str = "en-IN",
        on_transcript: Optional[Callable] = None,
        on_speech_start: Optional[Callable] = None,
        on_speech_end: Optional[Callable] = None,
    ):
        self._project = project
        self._location = "global"  # Chirp 2 requires global location
        self._language_code = language_code
        self._on_transcript = on_transcript
        self._on_speech_start = on_speech_start
        self._on_speech_end = on_speech_end
        self._connected = False
        self._audio_buffer: list[bytes] = []
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    async def connect(self) -> bool:
        """Initialize the Google STT client."""
        try:
            from google.cloud.speech_v2 import SpeechAsyncClient
            from google.cloud.speech_v2.types import cloud_speech
            self._client = SpeechAsyncClient()
            self._connected = True
            self._loop = asyncio.get_running_loop()
            logger.info("GoogleStreamingSTT: connected (project=%s)", self._project)
            return True
        except Exception as exc:
            logger.error("GoogleStreamingSTT: connection failed: %s", exc)
            return False

    async def send_audio(self, audio_bytes: bytes) -> None:
        """Buffer raw PCM audio chunks."""
        if not self._connected:
            return
        self._audio_buffer.append(audio_bytes)

    async def flush_buffer(self) -> None:
        """Send buffered audio to Google STT for recognition."""
        if not self._connected or not self._audio_buffer:
            return

        pcm_data = b"".join(self._audio_buffer)
        self._audio_buffer = []

        if len(pcm_data) < 1600:  # Less than 100ms of audio, skip
            return

        try:
            from google.cloud.speech_v2.types import cloud_speech

            # Build the recognition request
            config = cloud_speech.RecognitionConfig(
                auto_decoding_config=cloud_speech.AutoDetectDecodingConfig(),
                language_codes=[self._language_code],
                model="chirp_2",
            )

            request = cloud_speech.RecognizeRequest(
                recognizer=f"projects/{self._project}/locations/{self._location}/recognizers/_",
                config=config,
                content=pcm_data,
            )

            response = await self._client.recognize(request=request)

            for result in response.results:
                if result.alternatives:
                    text = result.alternatives[0].transcript.strip()
                    if text:
                        logger.info("GoogleStreamingSTT: TRANSCRIPT: %s", text)
                        if self._on_transcript:
                            self._on_transcript(
                                StreamingTranscript(
                                    text=text,
                                    is_final=True,
                                    language_code=self._language_code,
                                )
                            )
        except Exception as exc:
            logger.error("GoogleStreamingSTT: recognition failed: %s", exc)

    async def flush(self) -> None:
        """No-op for Google STT (flush is handled in flush_buffer)."""
        pass

    async def close(self) -> None:
        """Close the client."""
        self._connected = False
        logger.info("GoogleStreamingSTT: closed")

"""Sarvam AI Real-time Streaming Clients - WebSocket-based STT and TTS.

This module provides real-time streaming speech-to-text and text-to-speech
using Sarvam's WebSocket APIs for ultra-low latency conversational AI.
"""
from __future__ import annotations

import asyncio
import base64
import inspect
import json
import logging
import os
from dataclasses import dataclass
from typing import Callable, Optional

import websockets

logger = logging.getLogger(__name__)

# Sarvam WebSocket endpoints
SARVAM_STT_WS_URL = "wss://api.sarvam.ai/speech-to-text/ws"
SARVAM_TTS_WS_URL = "wss://api.sarvam.ai/text-to-speech/streaming"


@dataclass
class StreamingTranscript:
    """Transcript result from streaming STT."""
    text: str
    is_final: bool = True
    language_code: Optional[str] = None


class SarvamStreamingSTT:
    """WebSocket-based streaming Speech-to-Text using Sarvam Saaras v3.

    API constraint (confirmed via live test 2026-03-18):
    - message encoding field MUST be 'audio/wav' (enum enforced server-side)
    - BUT sending a WAV header on every 20ms chunk produces silent failure
      because each tiny WAV file is too short for VAD/ASR to process

    Correct approach:
    - Buffer raw PCM frames while user is speaking
    - On speech_end (or EOU silence), send ONE complete WAV containing the
      full utterance, then flush
    - This satisfies the audio/wav encoding requirement AND gives the model
      enough audio context to produce a transcript
    """

    def __init__(
        self,
        api_key: str,
        language_code: str = "en-IN",
        model: str = "saaras:v3",
        mode: str = "transcribe",
        sample_rate: int = 16000,
        on_transcript: Optional[Callable[[StreamingTranscript], None]] = None,
        on_speech_start: Optional[Callable[[], None]] = None,
        on_speech_end: Optional[Callable[[], None]] = None,
    ):
        self._api_key = api_key
        self._language_code = language_code
        self._model = model
        self._mode = mode
        self._sample_rate = sample_rate
        self._on_transcript = on_transcript
        self._on_speech_start = on_speech_start
        self._on_speech_end = on_speech_end

        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._connected = False
        self._receive_task: Optional[asyncio.Task] = None
        self._current_transcript = ""
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        # Audio buffer: accumulate raw PCM chunks, send as one WAV per utterance
        self._audio_buffer: list[bytes] = []
        self._is_speaking: bool = False

    def _invoke_callback(self, callback: Optional[Callable], *args) -> None:
        """Invoke a callback, handling both sync and async callbacks."""
        if callback is None:
            return
        try:
            result = callback(*args)
            if inspect.isawaitable(result) and self._loop:
                asyncio.ensure_future(result, loop=self._loop)
        except Exception as e:
            logger.error("SarvamStreamingSTT: Callback error: %s", e)

    async def connect(self) -> bool:
        """Establish WebSocket connection to Sarvam STT streaming API."""
        try:
            # input_audio_codec=wav because message encoding must be 'audio/wav'
            # (API enforces this as an enum — pcm_s16le is rejected at message level)
            # We buffer PCM locally and send one complete WAV per utterance.
            params = {
                "model": self._model,
                "mode": self._mode,
                "language-code": self._language_code,
                "sample_rate": str(self._sample_rate),
                "input_audio_codec": "wav",
                "high_vad_sensitivity": "true",
                "vad_signals": "true",
            }
            query_string = "&".join(f"{k}={v}" for k, v in params.items())
            url = f"{SARVAM_STT_WS_URL}?{query_string}"

            headers = {"Api-Subscription-Key": self._api_key}  # Capitalized header name
            
            # Debug: log URL and partial API key
            logger.info(f"SarvamStreamingSTT: URL: {url}")
            logger.info(f"SarvamStreamingSTT: API Key (first 8 chars): {self._api_key[:8]}...")

            # Use extra_headers (websockets 13.x API)
            self._ws = await websockets.connect(url, extra_headers=headers)
            self._connected = True
            self._loop = asyncio.get_running_loop()
            logger.info("SarvamStreamingSTT: Creating receive task...")
            self._receive_task = asyncio.create_task(self._receive_loop())
            logger.info("SarvamStreamingSTT: Receive task created, connected to streaming STT")
            return True
        except Exception as exc:
            logger.error("SarvamStreamingSTT: Connection failed: %s", exc)
            return False

    def _pcm_to_wav(self, pcm_data: bytes) -> bytes:
        """Wrap raw PCM data in a WAV header for Sarvam API."""
        import struct
        import io
        
        wav_buffer = io.BytesIO()
        
        # WAV header parameters
        num_channels = 1
        sample_rate = self._sample_rate
        bits_per_sample = 16
        byte_rate = sample_rate * num_channels * 2
        block_align = num_channels * 2
        data_size = len(pcm_data)
        
        # RIFF chunk
        wav_buffer.write(b'RIFF')
        wav_buffer.write(struct.pack('<I', 36 + data_size))
        wav_buffer.write(b'WAVE')
        
        # fmt sub-chunk
        wav_buffer.write(b'fmt ')
        wav_buffer.write(struct.pack('<I', 16))
        wav_buffer.write(struct.pack('<H', 1))   # PCM format
        wav_buffer.write(struct.pack('<H', num_channels))
        wav_buffer.write(struct.pack('<I', sample_rate))
        wav_buffer.write(struct.pack('<I', byte_rate))
        wav_buffer.write(struct.pack('<H', block_align))
        wav_buffer.write(struct.pack('<H', bits_per_sample))
        
        # data sub-chunk
        wav_buffer.write(b'data')
        wav_buffer.write(struct.pack('<I', data_size))
        wav_buffer.write(pcm_data)
        
        return wav_buffer.getvalue()

    async def send_audio(self, audio_bytes: bytes) -> None:
        """Buffer raw PCM audio. Call flush_buffer() to send as one WAV.

        The Sarvam message API requires encoding='audio/wav' (enum enforced).
        Sending a WAV header on every 20ms chunk causes silent failure because
        each tiny file is too short for the model to process.

        Instead: buffer all PCM here, send ONE complete WAV per utterance
        via flush_buffer() when EOU/speech_end fires.
        """
        if not self._connected:
            return
        self._audio_buffer.append(audio_bytes)

    async def flush_buffer(self) -> None:
        """Send all buffered PCM as one complete WAV file, then flush.

        Call this when EOU detector or speech_end fires.
        Clears the buffer after sending.
        """
        if not self._connected or not self._ws:
            return
        if not self._audio_buffer:
            logger.debug("SarvamStreamingSTT: flush_buffer called with empty buffer")
            return

        try:
            pcm_data = b"".join(self._audio_buffer)
            self._audio_buffer = []
            wav_bytes = self._pcm_to_wav(pcm_data)
            audio_b64 = base64.b64encode(wav_bytes).decode("utf-8")
            message = {
                "audio": {
                    "data": audio_b64,
                    "encoding": "audio/wav",
                    "sample_rate": self._sample_rate,
                },
            }
            await self._ws.send(json.dumps(message))
            await self._ws.send(json.dumps({"type": "flush"}))
            logger.info(
                "SarvamStreamingSTT: Sent buffered WAV (%d bytes PCM, %d bytes WAV)",
                len(pcm_data), len(wav_bytes)
            )
        except Exception as exc:
            logger.error("SarvamStreamingSTT: flush_buffer failed: %s", exc)

    async def flush(self) -> None:
        """Send flush signal only (no audio). Use flush_buffer() to send audio."""
        if not self._connected or not self._ws:
            return
        try:
            await self._ws.send(json.dumps({"type": "flush"}))
        except Exception as exc:
            logger.error("SarvamStreamingSTT: Flush failed: %s", exc)

    async def _receive_loop(self) -> None:
        """Receive and process messages from STT WebSocket.
        
        IMPORTANT: Do NOT add any pre-loop recv() call here.
        The async-for loop handles ALL messages including the first one.
        A separate recv() before the loop will silently consume real messages
        (transcripts, speech_start events) and they will be lost.
        """
        logger.info("SarvamStreamingSTT: _receive_loop started")
        try:
            async for message in self._ws:
                logger.info(f"SarvamStreamingSTT: Raw received: {message[:500]}")
                try:
                    data = json.loads(message)
                    msg_type = data.get("type")
                    logger.info(f"SarvamStreamingSTT: Received message type={msg_type}")

                    if msg_type == "events":
                        # VAD signals: {"type":"events","data":{"signal_type":"START_SPEECH",...}}
                        signal_type = data.get("data", {}).get("signal_type", "")
                        if signal_type == "START_SPEECH":
                            logger.info("SarvamStreamingSTT: Speech started")
                            self._invoke_callback(self._on_speech_start)
                            self._current_transcript = ""
                        elif signal_type == "END_SPEECH":
                            logger.info("SarvamStreamingSTT: Speech ended")
                            self._invoke_callback(self._on_speech_end)

                    elif msg_type == "data":
                        # Transcript result: {"type":"data","data":{"transcript":"...","language_code":"..."}}
                        inner = data.get("data", {})
                        text = inner.get("transcript", "")
                        logger.info(f"SarvamStreamingSTT: TRANSCRIPT: {text}")
                        if text:
                            self._current_transcript = text
                            self._invoke_callback(
                                self._on_transcript,
                                StreamingTranscript(
                                    text=text,
                                    is_final=True,
                                    language_code=inner.get("language_code"),
                                )
                            )

                    else:
                        logger.debug(f"SarvamStreamingSTT: Unhandled message type={msg_type}")

                except json.JSONDecodeError:
                    logger.warning("SarvamStreamingSTT: Invalid JSON received")
        except websockets.exceptions.ConnectionClosed as e:
            logger.info(f"SarvamStreamingSTT: Connection closed: code={e.code}, reason={e.reason}")
        except Exception as exc:
            logger.error("SarvamStreamingSTT: Receive error: %s", exc)
        finally:
            self._connected = False

    async def close(self) -> None:
        """Close the WebSocket connection."""
        self._connected = False
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
        if self._ws:
            await self._ws.close()
            self._ws = None


class SarvamStreamingTTS:
    """WebSocket-based streaming Text-to-Speech using Sarvam Bulbul v3."""

    def __init__(
        self,
        api_key: str,
        language_code: str = "en-IN",
        speaker: str = "shubh",
        model: str = "bulbul:v3",
        sample_rate: int = 16000,
        on_audio_chunk: Optional[Callable[[bytes], None]] = None,
        on_complete: Optional[Callable[[], None]] = None,
    ):
        self._api_key = api_key
        self._language_code = language_code
        self._speaker = speaker
        self._model = model
        self._sample_rate = sample_rate
        self._on_audio_chunk = on_audio_chunk
        self._on_complete = on_complete

        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._connected = False
        self._receive_task: Optional[asyncio.Task] = None
        self._configured = False

    async def connect(self) -> bool:
        """Establish WebSocket connection to Sarvam TTS streaming API."""
        try:
            url = f"{SARVAM_TTS_WS_URL}?model={self._model}&send_completion_event=true"
            headers = {"Api-Subscription-Key": self._api_key}  # Capitalized header name

            # Use extra_headers (websockets 13.x API)
            self._ws = await websockets.connect(url, extra_headers=headers)
            self._connected = True
            self._receive_task = asyncio.create_task(self._receive_loop())

            # Send configuration
            config = {
                "type": "config",
                "data": {
                    "speaker": self._speaker,
                    "target_language_code": self._language_code,
                    "pace": 1.0,
                    "output_audio_codec": "pcm_s16le",
                    "output_audio_bitrate": "128k",
                }
            }
            await self._ws.send(json.dumps(config))
            self._configured = True

            logger.info("SarvamStreamingTTS: Connected to streaming TTS")
            return True
        except Exception as exc:
            logger.error("SarvamStreamingTTS: Connection failed: %s", exc)
            return False

    async def send_text(self, text: str) -> None:
        """Send text to be synthesized."""
        if not self._connected or not self._ws or not self._configured:
            logger.warning("SarvamStreamingTTS: Not ready to send text")
            return

        try:
            message = {
                "type": "text",
                "data": {"text": text}
            }
            await self._ws.send(json.dumps(message))
            # Flush to trigger processing
            await self._ws.send(json.dumps({"type": "flush"}))
        except Exception as exc:
            logger.error("SarvamStreamingTTS: Send failed: %s", exc)

    async def _receive_loop(self) -> None:
        """Receive and process audio chunks from TTS WebSocket."""
        try:
            async for message in self._ws:
                try:
                    data = json.loads(message)
                    msg_type = data.get("type")

                    if msg_type == "audio":
                        audio_b64 = data.get("data", {}).get("audio", "")
                        if audio_b64 and self._on_audio_chunk:
                            audio_bytes = base64.b64decode(audio_b64)
                            self._on_audio_chunk(audio_bytes)

                    elif msg_type == "event":
                        event_type = data.get("data", {}).get("event_type", "")
                        if event_type == "final" and self._on_complete:
                            self._on_complete()

                except json.JSONDecodeError:
                    logger.warning("SarvamStreamingTTS: Invalid JSON received")
                except Exception as exc:
                    logger.error("SarvamStreamingTTS: Processing error: %s", exc)
        except websockets.exceptions.ConnectionClosed:
            logger.info("SarvamStreamingTTS: Connection closed")
        except Exception as exc:
            logger.error("SarvamStreamingTTS: Receive error: %s", exc)
        finally:
            self._connected = False

    async def close(self) -> None:
        """Close the WebSocket connection."""
        self._connected = False
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
        if self._ws:
            await self._ws.close()
            self._ws = None


class SarvamRealtimePipeline:
    """Combined real-time STT and TTS pipeline for conversational AI."""

    def __init__(
        self,
        api_key: str,
        language_code: str = "en-IN",
        speaker: str = "shubh",
        stt_model: str = "saaras:v3",
        tts_model: str = "bulbul:v3",
        sample_rate: int = 16000,
        on_user_transcript: Optional[Callable[[str], None]] = None,
        on_agent_audio: Optional[Callable[[bytes], None]] = None,
        on_speech_start: Optional[Callable[[], None]] = None,
        on_speech_end: Optional[Callable[[], None]] = None,
    ):
        self._api_key = api_key
        self._stt = SarvamStreamingSTT(
            api_key=api_key,
            language_code=language_code,
            model=stt_model,
            sample_rate=sample_rate,
            on_transcript=self._on_stt_transcript,
            on_speech_start=on_speech_start,
            on_speech_end=self._on_speech_end,
        )
        self._tts = SarvamStreamingTTS(
            api_key=api_key,
            language_code=language_code,
            speaker=speaker,
            model=tts_model,
            sample_rate=sample_rate,
            on_audio_chunk=on_agent_audio,
        )
        self._on_user_transcript = on_user_transcript
        self._on_agent_audio = on_agent_audio
        self._pending_transcript = ""

    async def start(self) -> bool:
        """Start both STT and TTS connections."""
        stt_ok = await self._stt.connect()
        tts_ok = await self._tts.connect()
        return stt_ok and tts_ok

    async def stop(self) -> None:
        """Stop both STT and TTS connections."""
        await self._stt.close()
        await self._tts.close()

    async def send_audio(self, audio_bytes: bytes) -> None:
        """Send audio chunk to STT."""
        await self._stt.send_audio(audio_bytes)

    async def speak(self, text: str) -> None:
        """Send text to TTS for synthesis."""
        await self._tts.send_text(text)

    def _on_stt_transcript(self, transcript: StreamingTranscript) -> None:
        """Handle STT transcript."""
        if transcript.text:
            self._pending_transcript = transcript.text
            if self._on_user_transcript:
                self._on_user_transcript(transcript.text)

    def _on_speech_end(self) -> None:
        """Handle end of user speech."""
        # Can trigger processing here if needed
        pass

    @property
    def pending_transcript(self) -> str:
        """Get the pending transcript and clear it."""
        text = self._pending_transcript
        self._pending_transcript = ""
        return text

"""Pipecat audio pipeline — Sarvam Real-time Streaming STT/TTS, EOU detection, RPC bridge wiring.

Pipeline stages:
    Recall.ai audio stream
        → EOU Detector (silence threshold)
        → [real-time] Saaras v3 STT (WebSocket streaming)
        → RPC Bridge send (TurnMessage → pi_agent)
        → [on Turn_Output received] TTS Streaming Injector
        → Recall.ai audio injection
"""
from __future__ import annotations

import asyncio
import asyncio.subprocess
import io
import logging
import os
import struct
import time
import wave
from dataclasses import dataclass, field
from typing import Callable, Optional

import httpx

from pipeline.callbacks import EventPersistenceFn, LatencyRecordingFn, SessionSummaryFn, TurnPersistenceFn
from pipeline.eou_detector import EOUDetector
from pipeline.rpc_bridge import (
    TurnMessage,
    TurnOutputMessage,
    SessionStartMessage,
    SessionEndMessage,
    SessionSummaryMessage,
    serialize_rpc_message,
    parse_rpc_message,
)
from pipeline.tts_injector import TTSInjector
from pipeline.sarvam_realtime import SarvamStreamingSTT, SarvamStreamingTTS

logger = logging.getLogger(__name__)

# Seconds to wait for session_summary before force-terminating pi_agent
SESSION_SUMMARY_TIMEOUT_S: float = 5.0

# Safe fallback utterance when TTS/LLM pipeline fails
SAFE_FALLBACK_UTTERANCE = (
    "I'm sorry, I need a moment to process that. "
    "Could you give me just a second?"
)


@dataclass
class TranscriptSegment:
    """A single speaker's transcript segment for the current turn."""
    speaker: str
    text: str
    timestamp_ms: int


class AudioPipeline:
    """Long-lived audio pipeline for a single Vero session.

    Wires together:
    - pi_agent Node.js child process (spawned on start)
    - Real-time streaming STT (Sarvam Saaras v3 WebSocket)
    - EOUDetector (silence threshold, vero_speaking suppression)
    - RPC Bridge send (TurnMessage → pi_agent on turn_complete)
    - RPC Bridge receive (TurnOutputMessage → TTS Streaming Injector)

    Args:
        session_id: Unique session identifier for logging and RPC messages.
        skill_pack: Parsed SkillPack dict (used for tts_voice lookup and
                    session_start message).
        on_audio_inject: Callback to inject synthesised audio into Recall.ai.
        sarvam_api_key: Defaults to SARVAM_API_KEY env var.
    """

    def __init__(
        self,
        session_id: str,
        skill_pack: dict,
        on_audio_inject: Callable[[bytes], None],
        sarvam_api_key: Optional[str] = None,
        on_session_summary: Optional[SessionSummaryFn] = None,
        on_event: Optional[EventPersistenceFn] = None,
        on_latency_recorded: Optional[LatencyRecordingFn] = None,
        on_turn: Optional[TurnPersistenceFn] = None,
        llm_model: Optional[str] = None,
    ) -> None:
        self.session_id = session_id
        self._skill_pack = skill_pack
        self._on_audio_inject = on_audio_inject
        self._sarvam_key = sarvam_api_key or os.environ.get("SARVAM_API_KEY", "")
        self._on_session_summary = on_session_summary
        self._on_event = on_event
        self._on_latency_recorded = on_latency_recorded
        self._on_turn = on_turn
        self._db_turn_index: int = 0  # monotonic index for DB turn rows (user + agent)

        # LLM model determines STT provider
        # Google STT needs roles/speech.client IAM role. Using Sarvam until granted.
        self._llm_model = llm_model or skill_pack.get("agent", {}).get("model_preferences", [{}])[0].get("model", "sarvam-30b")
        self._use_google_stt = False

        # STT dispatch control.
        # Recall.ai is configured with Deepgram Nova-2 and sends transcripts via
        # the /webhooks/recall/transcription webhook (recall.py). That is the
        # single authoritative STT path. Sarvam STT on raw PCM runs in parallel
        # and must NOT dispatch turns to the agent, or every utterance arrives
        # twice causing confusion and score corruption.
        self._stt_dispatch_enabled: bool = False

        # pi_agent child process (set in _spawn_pi_agent)
        self._pi_process: Optional[asyncio.subprocess.Process] = None
        self._pi_stdin: Optional[asyncio.StreamWriter] = None
        self._pi_stdout: Optional[asyncio.StreamReader] = None
        self._pi_restart_count: int = 0
        self._stopping: bool = False

        # Current turn transcript accumulator
        self._current_turn_segments: list[TranscriptSegment] = []
        self._turn_index: int = 0

        # EOU detector — fires _on_turn_complete when silence threshold met
        # 2.5s silence prevents cutting off natural thinking pauses in technical speech
        eou_threshold = self._skill_pack.get("agent", {}).get("eou_threshold_seconds", 2.5)
        self._eou = EOUDetector(
            session_id=session_id,
            on_turn_complete=self._on_turn_complete,
            silence_duration=eou_threshold,
        )

        # Language and voice configuration
        language = skill_pack.get("agent", {}).get("language", "en-IN")
        # tts_voice is stored as "sarvam:shubh" — strip the prefix to get the speaker name
        tts_voice = skill_pack.get("agent", {}).get("tts_voice", "sarvam:shubh")
        speaker = tts_voice.split(":")[-1] if ":" in tts_voice else tts_voice

        # Real-time streaming STT
        self._stt: Optional[SarvamStreamingSTT] = None
        self._stt_connected = False
        self._current_transcript = ""

        # Real-time streaming TTS
        self._streaming_tts: Optional[SarvamStreamingTTS] = None
        self._tts_connected = False

        # Legacy TTS injector for fallback
        self._tts = TTSInjector(
            session_id=session_id,
            on_audio_chunk=on_audio_inject,
            on_vero_speaking=self._eou.set_vero_speaking,
            on_first_chunk_ready=self._record_first_audio_chunk,
            recall_bot_id=skill_pack.get("_recall_bot_id"),
            language=language,
        )

        # Latency tracking
        self._eou_timestamp_ms: Optional[int] = None
        self._first_audio_chunk_ms: Optional[int] = None

        # Turn dispatch guard - prevent double dispatch from EOU and speech_end
        self._turn_dispatched: bool = False

        # Accumulated transcript segments (combined when EOU fires)
        self._accumulated_segments: list[str] = []

        # Store event loop for cross-thread scheduling
        self._loop: Optional[asyncio.AbstractEventLoop] = None

        # Store config for streaming services
        self._language = language
        self._speaker = speaker

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Spawn pi_agent, connect streaming services, send session_start, start RPC loop."""
        self._loop = asyncio.get_event_loop()
        await self._spawn_pi_agent()

        # Initialize and connect real-time streaming STT
        # Use Google STT for non-Sarvam LLMs (better accuracy), Sarvam STT otherwise
        if self._use_google_stt:
            try:
                from pipeline.google_stt_adapter import GoogleStreamingSTTAdapter
                gcp_project = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
                if gcp_project:
                    self._stt = GoogleStreamingSTTAdapter(
                        project=gcp_project,
                        location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"),
                        language_code=self._language,
                        on_transcript=self._on_stt_transcript,
                        on_speech_start=self._on_speech_start,
                        on_speech_end=self._on_speech_end,
                    )
                    self._stt_connected = await self._stt.connect()
                    if self._stt_connected:
                        logger.info("pipeline[%s]: Google streaming STT connected", self.session_id)
                    else:
                        logger.warning("pipeline[%s]: Google STT failed, falling back to Sarvam", self.session_id)
                        self._use_google_stt = False
                else:
                    logger.info("pipeline[%s]: no GOOGLE_CLOUD_PROJECT, using Sarvam STT", self.session_id)
                    self._use_google_stt = False
            except ImportError:
                logger.warning("pipeline[%s]: Google STT adapter not available, using Sarvam STT", self.session_id)
                self._use_google_stt = False

        if not self._use_google_stt:
            self._stt = SarvamStreamingSTT(
                api_key=self._sarvam_key,
                language_code=self._language,
                model="saaras:v3",
                mode="transcribe",
                sample_rate=16000,
                on_transcript=self._on_stt_transcript,
                on_speech_start=self._on_speech_start,
                on_speech_end=self._on_speech_end,
            )
            self._stt_connected = await self._stt.connect()
            if self._stt_connected:
                logger.info("pipeline[%s]: Sarvam streaming STT connected", self.session_id)
            else:
                logger.error("pipeline[%s]: failed to connect streaming STT", self.session_id)

        # Streaming TTS WebSocket endpoint is not yet available — skip and use HTTP TTS fallback
        self._streaming_tts = None
        self._tts_connected = False
        logger.info("pipeline[%s]: using HTTP TTS fallback (streaming TTS disabled)", self.session_id)

        # Send session_start over RPC Bridge
        start_msg = SessionStartMessage(
            session_id=self.session_id,
            skill_pack=self._skill_pack,
        )
        await self._write_rpc(start_msg)
        logger.info("pipeline[%s]: sent SessionStartMessage", self.session_id)

        asyncio.ensure_future(self._rpc_receive_loop())

    async def stop(self) -> None:
        """Send session_end, close streaming services, await session_summary, then terminate pi_agent."""
        self._stopping = True

        # Close streaming connections
        if self._stt:
            await self._stt.close()
            logger.info("pipeline[%s]: streaming STT closed", self.session_id)
        if self._streaming_tts:
            await self._streaming_tts.close()
            logger.info("pipeline[%s]: streaming TTS closed", self.session_id)

        # Send session_end and wait up to SESSION_SUMMARY_TIMEOUT_S for summary
        if self._pi_process is not None and self._pi_process.returncode is None:
            end_msg = SessionEndMessage(
                session_id=self.session_id,
                reason="manual",
            )
            try:
                await self._write_rpc(end_msg)
                logger.info("pipeline[%s]: sent SessionEndMessage", self.session_id)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "pipeline[%s]: failed to send SessionEndMessage: %s", self.session_id, exc
                )

            # Give pi_agent time to flush session_summary
            await asyncio.sleep(SESSION_SUMMARY_TIMEOUT_S)

            # Terminate the process
            try:
                self._pi_process.terminate()
                await asyncio.wait_for(self._pi_process.wait(), timeout=3.0)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "pipeline[%s]: error terminating pi_agent: %s", self.session_id, exc
                )

    # ------------------------------------------------------------------
    # pi_agent child process management
    # ------------------------------------------------------------------

    async def _spawn_pi_agent(self) -> None:
        """Spawn `node agent/agent.ts` as an asyncio subprocess.

        Sets self._pi_process, self._pi_stdin, self._pi_stdout and starts
        a background task to drain stderr to the logger.
        """
        logger.info("pipeline[%s]: spawning pi_agent", self.session_id)
        self._pi_process = await asyncio.create_subprocess_exec(
            "node",
            "agent/dist/agent.js",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._pi_stdin = self._pi_process.stdin
        self._pi_stdout = self._pi_process.stdout
        logger.info(
            "pipeline[%s]: pi_agent spawned pid=%d", self.session_id, self._pi_process.pid
        )
        # Drain stderr in background so it doesn't block the process
        asyncio.ensure_future(self._drain_pi_stderr())

    async def _drain_pi_stderr(self) -> None:
        """Read pi_agent stderr and forward each line to the logger."""
        if self._pi_process is None or self._pi_process.stderr is None:
            return
        try:
            while True:
                line = await self._pi_process.stderr.readline()
                if not line:
                    break
                logger.info(
                    "pipeline[%s]: pi_agent stderr: %s",
                    self.session_id,
                    line.decode("utf-8", errors="replace").rstrip(),
                )
        except Exception as exc:  # noqa: BLE001
            logger.debug("pipeline[%s]: pi_agent stderr reader ended: %s", self.session_id, exc)

    async def _write_rpc(self, msg: object) -> None:
        """Serialise *msg* and write it to pi_agent stdin."""
        if self._pi_stdin is None:
            raise RuntimeError("pi_agent stdin not available")
        line = serialize_rpc_message(msg)
        self._pi_stdin.write(line.encode())
        await self._pi_stdin.drain()

    # ------------------------------------------------------------------
    # Audio ingestion (called per Recall.ai audio frame)
    # ------------------------------------------------------------------

    def process_audio_frame(self, audio_chunk: bytes) -> None:
        """Feed one raw PCM audio frame through the pipeline.

        Streams audio to real-time STT and feeds the EOU detector.
        """
        # Feed EOU detector
        self._eou.process_frame(audio_chunk)

        # Stream to real-time STT
        if self._stt_connected and self._stt:
            asyncio.ensure_future(self._stt.send_audio(audio_chunk))

    # ------------------------------------------------------------------
    # Real-time Streaming STT handlers
    # ------------------------------------------------------------------

    def _on_stt_transcript(self, transcript) -> None:
        """Handle streaming STT transcript — accumulate all received text."""
        text = transcript.text if hasattr(transcript, 'text') else str(transcript)
        if text.strip():
            # Accumulate into segments directly (don't overwrite)
            self._accumulated_segments.append(text.strip())
            logger.debug("pipeline[%s]: STT segment: %s (total segments: %d)", 
                        self.session_id, text[:50], len(self._accumulated_segments))

    def _on_speech_start(self) -> None:
        """Handle speech start detection."""
        self._current_transcript = ""
        logger.debug("pipeline[%s]: Speech started", self.session_id)

    def _on_speech_end(self) -> None:
        """Handle speech end from Sarvam VAD.
        
        NOTE: Sarvam VAD fires rapidly when processing batched audio from Recall.ai.
        Do NOT dispatch on speech_end — just accumulate text. The EOU detector
        (silence threshold on raw audio frames) determines when the person is truly done.
        """
        logger.debug("pipeline[%s]: Speech ended (Sarvam VAD) — accumulating only", self.session_id)
        # Just flush STT buffer to get the transcript text, don't dispatch
        asyncio.ensure_future(self._accumulate_transcript())

    async def _accumulate_transcript(self) -> None:
        """Flush STT buffer to trigger transcript delivery. Segments are accumulated in _on_stt_transcript."""
        if self._stt:
            await self._stt.flush_buffer()    

    async def _flush_and_dispatch(self) -> None:
        """Send buffered audio as WAV, wait for transcript, then dispatch turn."""
        # Send buffered PCM as one complete WAV to get the transcript
        if self._stt:
            await self._stt.flush_buffer()

        # Wait for transcript message to arrive from Sarvam (up to 3s)
        deadline = asyncio.get_event_loop().time() + 3.0
        while asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(0.05)
            if self._current_transcript.strip():
                break

        # Guard: skip if already dispatched or Vero is speaking
        if self._turn_dispatched or self._eou._vero_speaking:
            logger.debug("pipeline[%s]: flush_and_dispatch skipped", self.session_id)
            return

        transcript = self._current_transcript.strip()
        if not transcript:
            logger.debug("pipeline[%s]: flush_and_dispatch: no transcript after 3s", self.session_id)
            return

        self._turn_dispatched = True
        self._current_transcript = ""
        self._eou_timestamp_ms = int(time.monotonic() * 1000)
        await self._send_turn_message(self.session_id, transcript)
        self._eou.reset()

    def _on_tts_audio_chunk(self, chunk: bytes) -> None:
        """Handle streaming TTS audio chunk."""
        if self._on_audio_inject:
            self._on_audio_inject(chunk)

    # ------------------------------------------------------------------
    # EOU → RPC Bridge send
    # ------------------------------------------------------------------

    def _on_turn_complete(self, session_id: str) -> None:
        """Called by EOUDetector when silence threshold met.
        Combine all accumulated transcript segments and dispatch as one complete turn.
        """
        if not self._stt_dispatch_enabled:
            # Deepgram (via Recall.ai transcription webhook) is the authoritative
            # STT path. Suppress Sarvam STT dispatch to prevent double-turns.
            logger.debug("pipeline[%s]: turn_complete suppressed (stt_dispatch_enabled=False)", session_id)
            return
        if self._eou._vero_speaking or self._turn_dispatched:
            logger.debug(
                "pipeline[%s]: turn_complete suppressed (vero_speaking=%s, already_dispatched=%s)",
                session_id, self._eou._vero_speaking, self._turn_dispatched
            )
            return
        # Combine accumulated segments + any current transcript into one turn
        asyncio.ensure_future(self._dispatch_accumulated_turn())

    async def _dispatch_accumulated_turn(self) -> None:
        """Combine accumulated segments and dispatch as one complete turn."""
        # Flush STT buffer to get any remaining transcript.
        # Wait 1.5s for Sarvam to return the transcript for the last audio chunk
        # (previously 0.2s, which dropped the final sentence of long answers).
        if self._stt:
            await self._stt.flush_buffer()
            await asyncio.sleep(1.5)

        # Add any remaining current transcript
        if self._current_transcript.strip():
            self._accumulated_segments.append(self._current_transcript.strip())
            self._current_transcript = ""

        # Combine all segments into one turn
        full_transcript = " ".join(self._accumulated_segments).strip()
        self._accumulated_segments = []

        if not full_transcript:
            logger.debug("pipeline[%s]: dispatch_accumulated: no transcript", self.session_id)
            return

        # Short-fragment guard: if < 6 words, wait up to 2s for more content.
        # Prevents dangling fragments like "Vehicles." or "in the trucks." from
        # being dispatched as complete turns.
        if len(full_transcript.split()) < 6 and not self._turn_dispatched:
            logger.debug("pipeline[%s]: short fragment (%d words), waiting 2s for continuation",
                        self.session_id, len(full_transcript.split()))
            await asyncio.sleep(2.0)
            if self._current_transcript.strip():
                self._accumulated_segments.append(self._current_transcript.strip())
                self._current_transcript = ""
            if self._accumulated_segments:
                extra = " ".join(self._accumulated_segments).strip()
                self._accumulated_segments = []
                full_transcript = (full_transcript + " " + extra).strip()

        # Semantic continuation guard: if transcript ends with a conjunction,
        # preposition, or article the speaker clearly isn't done yet.
        # e.g. "with b m twenty five and" — wait extra 2s for the rest.
        _CONTINUATION_WORDS = {
            "and", "or", "but", "nor", "so", "yet", "for",
            "because", "since", "although", "while", "when", "where", "as",
            "if", "unless", "until", "after", "before", "though", "which",
            "that", "who", "what", "how", "in", "on", "at", "by", "with",
            "about", "from", "to", "of", "the", "a", "an", "this", "these",
        }
        last_word = full_transcript.rstrip(".,?!;:").split()[-1].lower() if full_transcript.split() else ""
        if last_word in _CONTINUATION_WORDS and not self._turn_dispatched:
            logger.debug("pipeline[%s]: transcript ends with '%s' (continuation word), waiting 2s",
                        self.session_id, last_word)
            await asyncio.sleep(2.0)
            if self._current_transcript.strip():
                self._accumulated_segments.append(self._current_transcript.strip())
                self._current_transcript = ""
            if self._accumulated_segments:
                extra = " ".join(self._accumulated_segments).strip()
                self._accumulated_segments = []
                full_transcript = (full_transcript + " " + extra).strip()

        if self._turn_dispatched:
            return

        self._turn_dispatched = True
        self._eou_timestamp_ms = int(time.monotonic() * 1000)
        logger.info("pipeline[%s]: dispatching full turn: %s", self.session_id, full_transcript[:80])
        await self._send_turn_message(self.session_id, full_transcript)
        self._eou.reset()

    async def _send_turn_message(self, session_id: str, transcript: str) -> None:
        """Send TurnMessage to pi_agent with the captured transcript."""
        speaker = "participant"

        msg = TurnMessage(
            session_id=session_id,
            speaker=speaker,
            transcript=transcript,
            turn_index=self._turn_index,
            timestamp_ms=int(time.time() * 1000),
        )

        # Persist user turn to DB
        if self._on_turn is not None:
            db_idx = self._db_turn_index
            self._db_turn_index += 1
            asyncio.ensure_future(self._on_turn(
                session_id, db_idx, speaker, transcript,
                msg.timestamp_ms, None, None, None, None, None, None,
            ))

        try:
            await self._write_rpc(msg)
            logger.info(
                "pipeline[%s]: sent TurnMessage turn_index=%d speaker=%s",
                session_id,
                self._turn_index,
                speaker,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("pipeline[%s]: failed to send TurnMessage: %s", session_id, exc)

        self._turn_index += 1
        # NOTE: _turn_dispatched stays True here.
        # It is reset in _handle_turn_output once the agent responds,
        # so no second fragment can interrupt while the agent is thinking.
        self._eou.reset()

    # ------------------------------------------------------------------
    # RPC Bridge receive → TTS Injector
    # ------------------------------------------------------------------

    async def _rpc_receive_loop(self) -> None:
        """Read TurnOutputMessages from pi_agent stdout and drive TTS injection."""
        logger.info("pipeline[%s]: RPC receive loop started", self.session_id)
        try:
            while True:
                if self._pi_stdout is None:
                    break

                # Read one JSONL line from pi_agent stdout (asyncio StreamReader)
                line_bytes = await self._pi_stdout.readline()
                if not line_bytes:
                    # stdout closed — pi_agent process ended
                    if self._stopping:
                        logger.info("pipeline[%s]: pi_agent stdout closed (stopping)", self.session_id)
                        break

                    # Unexpected closure — attempt restart
                    logger.warning(
                        "pipeline[%s]: pi_agent stdout closed unexpectedly — attempting restart",
                        self.session_id,
                    )
                    restarted = await self._restart_pi_agent()
                    if not restarted:
                        logger.error(
                            "pipeline[%s]: pi_agent restart failed — closing session",
                            self.session_id,
                        )
                        break
                    # Continue reading from the new stdout
                    continue

                line = line_bytes.decode("utf-8", errors="replace")
                msg = parse_rpc_message(line)

                if isinstance(msg, dict) and msg.get("type") == "error":
                    logger.warning(
                        "pipeline[%s]: RPC parse error: %s", self.session_id, msg.get("message")
                    )
                    continue

                if isinstance(msg, TurnOutputMessage):
                    # Persist agent turn to DB before TTS so it's in DB even if TTS fails
                    if self._on_turn is not None:
                        db_idx = self._db_turn_index
                        self._db_turn_index += 1
                        asyncio.ensure_future(self._on_turn(
                            msg.session_id, db_idx, "vero", msg.next_utterance,
                            int(time.time() * 1000),
                            msg.question_id, msg.score, msg.score_rationale,
                            msg.competency, msg.flags, msg.action,
                        ))
                    await self._handle_turn_output(msg)
                elif isinstance(msg, SessionSummaryMessage):
                    logger.info(
                        "pipeline[%s]: received SessionSummaryMessage — %d scores",
                        self.session_id,
                        len(msg.scores),
                    )
                    # Forward summary to backend for report generation via callback
                    if self._on_session_summary is not None:
                        try:
                            import dataclasses as _dc
                            await self._on_session_summary(self.session_id, _dc.asdict(msg))
                        except Exception as exc:  # noqa: BLE001
                            logger.warning(
                                "pipeline[%s]: failed to store session summary: %s",
                                self.session_id,
                                exc,
                            )
                else:
                    logger.debug(
                        "pipeline[%s]: received non-TurnOutput message type=%s",
                        self.session_id,
                        getattr(msg, "type", type(msg).__name__),
                    )
        except asyncio.CancelledError:
            logger.info("pipeline[%s]: RPC receive loop cancelled", self.session_id)
        except Exception as exc:  # noqa: BLE001
            logger.error("pipeline[%s]: RPC receive loop error: %s", self.session_id, exc)

    async def _restart_pi_agent(self) -> bool:
        """Attempt to restart pi_agent after unexpected process death.

        Returns True if restart succeeded and session_start was re-sent,
        False if the restart limit has been reached or spawn failed.
        """
        if self._pi_restart_count >= 1:  # PI_AGENT_MAX_RESTARTS
            logger.error(
                "pipeline[%s]: pi_agent restart limit reached — giving up",
                self.session_id,
            )
            return False

        self._pi_restart_count += 1
        logger.warning(
            "pipeline[%s]: restarting pi_agent (attempt %d)",
            self.session_id,
            self._pi_restart_count,
        )

        try:
            await self._spawn_pi_agent()
            start_msg = SessionStartMessage(
                session_id=self.session_id,
                skill_pack=self._skill_pack,
            )
            await self._write_rpc(start_msg)
            # Unlock the pipeline — the crashed agent never called _handle_turn_output
            self._turn_dispatched = False
            logger.info(
                "pipeline[%s]: pi_agent restarted successfully — re-sent SessionStartMessage",
                self.session_id,
            )
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "pipeline[%s]: pi_agent restart failed: %s", self.session_id, exc
            )
            return False

    async def _handle_turn_output(self, msg: TurnOutputMessage) -> None:
        """Handle a TurnOutputMessage: synthesise and inject audio via streaming TTS.

        Uses real-time streaming TTS for ultra-low latency.
        """
        # Agent has responded — unlock the pipeline so the next candidate turn
        # can be accepted. This was held True since _send_turn_message to prevent
        # mid-answer fragments from being dispatched as separate turns.
        self._turn_dispatched = False

        utterance = msg.next_utterance or SAFE_FALLBACK_UTTERANCE

        logger.info(
            "pipeline[%s]: TurnOutput received action=%s — streaming TTS",
            self.session_id,
            msg.action,
        )

        try:
            # Use streaming TTS if connected
            if self._tts_connected and self._streaming_tts:
                await self._streaming_tts.send_text(utterance)
            else:
                # Fallback to legacy TTS
                tts_voice = self._skill_pack.get("agent", {}).get("tts_voice", "sarvam:shubh")
                await self._tts.synthesise_and_inject(utterance, tts_voice)

            # Update cooldown in transcript session state to prevent feedback loop
            from backend.routers.recall import _transcript_sessions
            import time as _time
            if self.session_id in _transcript_sessions:
                # Set cooldown: ignore transcripts for the duration of the TTS + buffer
                # Estimate TTS duration: ~150 words/min = 2.5 words/sec
                word_count = len(utterance.split())
                estimated_tts_duration = max(3.0, word_count / 2.5)
                _transcript_sessions[self.session_id]["last_agent_response_time"] = _time.time() + estimated_tts_duration
                logger.debug("pipeline[%s]: set cooldown for %.1fs", self.session_id, estimated_tts_duration)

        except Exception as exc:  # noqa: BLE001
            logger.error(
                "pipeline[%s]: TTS injection failed: %s — using fallback", self.session_id, exc
            )
            try:
                tts_voice = self._skill_pack.get("agent", {}).get("tts_voice", "sarvam:shubh")
                await self._tts.synthesise_and_inject(SAFE_FALLBACK_UTTERANCE, tts_voice)
            except Exception as fallback_exc:  # noqa: BLE001
                logger.error(
                    "pipeline[%s]: fallback TTS also failed: %s", self.session_id, fallback_exc
                )

    def _record_first_audio_chunk(self, timestamp_ms: int) -> None:
        """Record the first_audio_chunk_ms timestamp for latency logging."""
        self._first_audio_chunk_ms = timestamp_ms
        if self._eou_timestamp_ms is not None:
            latency = timestamp_ms - self._eou_timestamp_ms
            logger.info(
                "pipeline[%s]: first audio chunk ready — latency=%dms",
                self.session_id,
                latency,
            )
            if self._on_latency_recorded is not None:
                # turn_index was already incremented after _on_turn_complete, so use index - 1
                turn_index = max(0, self._turn_index - 1)
                try:
                    result = self._on_latency_recorded(
                        self.session_id, turn_index, self._eou_timestamp_ms, timestamp_ms
                    )
                    if asyncio.iscoroutine(result):
                        asyncio.ensure_future(result)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "pipeline[%s]: on_latency_recorded callback failed: %s",
                        self.session_id,
                        exc,
                    )

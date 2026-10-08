"""Callback protocols for pipeline-backend communication.

This module defines the interface between the pipeline layer and the backend layer,
preventing circular dependencies and layering violations.
"""
from __future__ import annotations

from typing import Any, Callable, Optional, Protocol


class SessionSummaryCallback(Protocol):
    """Callback for storing session summary from pipeline."""

    async def __call__(self, session_id: str, summary: dict) -> None:
        """Store session summary.

        Args:
            session_id: The session identifier.
            summary: Dict with keys: scores, transcript, questions_not_reached.
        """
        ...


class EventPersistenceCallback(Protocol):
    """Callback for persisting events to the database."""

    async def __call__(self, session_id: str, event_type: str, detail: dict) -> None:
        """Persist an event.

        Args:
            session_id: The session identifier.
            event_type: Type of event (e.g., 'stt_reconnect', 'tts_fallback').
            detail: Event-specific details.
        """
        ...


class LatencyRecordingCallback(Protocol):
    """Callback for recording turn latency metrics."""

    async def __call__(self, session_id: str, turn_index: int, eou_ms: int, first_audio_ms: int) -> None:
        """Record latency for a turn.

        Args:
            session_id: The session identifier.
            turn_index: Zero-based turn index.
            eou_ms: Timestamp when EOU fired.
            first_audio_ms: Timestamp when first audio chunk was ready.
        """
        ...


# Type aliases for convenience
SessionSummaryFn = Callable[[str, dict], Any]
EventPersistenceFn = Callable[[str, str, dict], Any]
LatencyRecordingFn = Callable[[str, int, int, int], Any]
# (session_id, turn_index, speaker, transcript, timestamp_ms, question_id, score, rationale, competency, flags, action)
TurnPersistenceFn = Callable[..., Any]

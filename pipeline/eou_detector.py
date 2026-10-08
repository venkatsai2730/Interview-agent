"""End-of-Utterance (EOU) Detector.

Monitors audio energy levels and emits a `turn_complete` event after
1.5 seconds of continuous silence following participant speech.

Suppression rule: while `vero_speaking` is True, no `turn_complete`
event is emitted regardless of silence duration (prevents Vero from
triggering a response to its own speech).
"""
from __future__ import annotations

import logging
import time
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# Silence threshold: RMS energy below this value is treated as silence.
# Tune per deployment environment.
SILENCE_ENERGY_THRESHOLD: float = 0.01

# Duration of continuous silence (seconds) required to fire turn_complete.
# 2.5s allows natural 2-3s thinking pauses in Indian English technical speech
# without fragmenting mid-sentence. Can be overridden via skill_pack config.
DEFAULT_SILENCE_DURATION_THRESHOLD: float = 2.5


class EOUDetector:
    """Stateful EOU detector for a single session.

    Usage::

        def on_turn_complete(session_id: str) -> None:
            ...

        detector = EOUDetector(session_id="sess_abc", on_turn_complete=on_turn_complete)
        detector.process_frame(audio_chunk)   # call for every audio frame
        detector.set_vero_speaking(True)      # suppress while Vero speaks
        detector.set_vero_speaking(False)     # re-enable after Vero finishes
    """

    def __init__(
        self,
        session_id: str,
        on_turn_complete: Callable[[str], None],
        silence_threshold: float = SILENCE_ENERGY_THRESHOLD,
        silence_duration: float = DEFAULT_SILENCE_DURATION_THRESHOLD,
    ) -> None:
        self.session_id = session_id
        self._on_turn_complete = on_turn_complete
        self._silence_threshold = silence_threshold
        self._silence_duration = silence_duration

        self._vero_speaking: bool = False
        self._silence_start: Optional[float] = None  # monotonic timestamp
        self._had_speech: bool = False  # at least one non-silent frame seen
        self._fired: bool = False  # turn_complete already fired for this turn

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_vero_speaking(self, speaking: bool) -> None:
        """Update the vero_speaking suppression flag.

        When set to True, any in-progress silence timer is paused and
        turn_complete will not fire. When set back to False, the timer
        resets so a fresh silence window is required.
        """
        self._vero_speaking = speaking
        if speaking:
            # Reset silence tracking so Vero's own trailing silence
            # doesn't immediately trigger a turn_complete after it stops.
            self._silence_start = None
            self._fired = False
        logger.debug(
            "eou[%s]: vero_speaking=%s", self.session_id, speaking
        )

    def process_frame(self, audio_chunk: bytes, sample_rate: int = 16000) -> None:
        """Process one audio frame and potentially emit turn_complete.

        Args:
            audio_chunk: Raw PCM bytes (16-bit signed, mono assumed).
            sample_rate: Sample rate in Hz (used only for logging context).
        """
        if self._vero_speaking:
            # Suppressed — do nothing regardless of energy level.
            return

        energy = _rms_energy(audio_chunk)
        is_silent = energy < self._silence_threshold
        now = time.monotonic()

        if not is_silent:
            # Non-silent frame: mark that speech has occurred and reset timer.
            self._had_speech = True
            self._silence_start = None
            self._fired = False
            return

        # Silent frame below threshold.
        if not self._had_speech:
            # Haven't heard any speech yet — don't start the silence timer.
            return

        if self._fired:
            # Already fired for this turn; wait for new speech.
            return

        if self._silence_start is None:
            # Start the silence window.
            self._silence_start = now
            return

        elapsed = now - self._silence_start
        if elapsed >= self._silence_duration:
            self._fired = True
            self._had_speech = False
            self._silence_start = None
            logger.info(
                "eou[%s]: turn_complete fired after %.2fs silence",
                self.session_id,
                elapsed,
            )
            self._on_turn_complete(self.session_id)

    def reset(self) -> None:
        """Reset all state (call at session start or after a turn is processed)."""
        self._silence_start = None
        self._had_speech = False
        self._fired = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rms_energy(audio_chunk: bytes) -> float:
    """Compute RMS energy of a 16-bit PCM audio chunk.

    Returns a normalised float in [0.0, 1.0].
    """
    if not audio_chunk:
        return 0.0
    import struct

    num_samples = len(audio_chunk) // 2
    if num_samples == 0:
        return 0.0

    samples = struct.unpack(f"<{num_samples}h", audio_chunk[:num_samples * 2])
    rms = (sum(s * s for s in samples) / num_samples) ** 0.5
    # Normalise: 16-bit max is 32768
    return rms / 32768.0

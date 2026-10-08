"""Unit tests for EOU (End-of-Utterance) Detector."""
from __future__ import annotations

import pytest
from unittest.mock import Mock, call

from pipeline.eou_detector import EOUDetector, DEFAULT_SILENCE_DURATION_THRESHOLD


class TestEOUDetector:
    """Test suite for EOUDetector."""

    def test_default_threshold(self):
        """Test that default threshold is 1.0s as per fix."""
        mock_callback = Mock()
        detector = EOUDetector(
            session_id="test_session",
            on_turn_complete=mock_callback,
        )
        assert detector._silence_duration == DEFAULT_SILENCE_DURATION_THRESHOLD
        assert detector._silence_duration == 1.0

    def test_custom_threshold_from_skill_pack(self):
        """Test that threshold can be configured via skill pack."""
        mock_callback = Mock()
        custom_threshold = 1.5
        detector = EOUDetector(
            session_id="test_session",
            on_turn_complete=mock_callback,
            silence_duration=custom_threshold,
        )
        assert detector._silence_duration == 1.5

    def test_threshold_bounds(self):
        """Test threshold accepts values within reasonable bounds."""
        mock_callback = Mock()

        # Minimum threshold
        detector_min = EOUDetector(
            session_id="test_session",
            on_turn_complete=mock_callback,
            silence_duration=0.5,
        )
        assert detector_min._silence_duration == 0.5

        # Maximum threshold
        detector_max = EOUDetector(
            session_id="test_session",
            on_turn_complete=mock_callback,
            silence_duration=3.0,
        )
        assert detector_max._silence_duration == 3.0

    def test_turn_complete_fires_after_silence_threshold(self):
        """Test that turn_complete fires after silence duration is met."""
        mock_callback = Mock()
        detector = EOUDetector(
            session_id="test_session",
            on_turn_complete=mock_callback,
            silence_duration=0.1,  # 100ms for fast test
            silence_threshold=0.001,  # Very low energy threshold
        )

        # Simulate speech (non-silent frame)
        import struct
        # Create audio frame with high energy
        audio_frame = struct.pack("<160h", *[1000] * 160)
        detector.process_frame(audio_frame)

        # Should not fire immediately after speech
        mock_callback.assert_not_called()

        # Simulate silence for threshold duration
        import time
        silent_frame = struct.pack("<160h", *[0] * 160)

        # Process silent frames - need to simulate time passing
        # Since we can't easily mock time.monotonic in the detector,
        # we'll verify the detector state changes correctly
        detector._silence_start = time.monotonic() - 0.2  # Set silence start in past
        detector._had_speech = True

        detector.process_frame(silent_frame)

        # Should have fired turn_complete
        mock_callback.assert_called_once_with("test_session")

    def test_vero_speaking_suppresses_turn_complete(self):
        """Test that turn_complete is suppressed while vero_speaking is True."""
        mock_callback = Mock()
        detector = EOUDetector(
            session_id="test_session",
            on_turn_complete=mock_callback,
            silence_duration=0.1,
        )

        # Set vero_speaking to True
        detector.set_vero_speaking(True)

        # Process frames - should not fire
        import struct
        import time

        silent_frame = struct.pack("<160h", *[0] * 160)
        detector._silence_start = time.monotonic() - 0.2
        detector._had_speech = True

        detector.process_frame(silent_frame)

        # Should not fire because vero_speaking is True
        mock_callback.assert_not_called()

        # Set vero_speaking to False
        detector.set_vero_speaking(False)

        # Reset and try again
        detector._silence_start = time.monotonic() - 0.2
        detector.process_frame(silent_frame)

        # Should fire now
        mock_callback.assert_called_once_with("test_session")

    def test_no_turn_complete_without_speech(self):
        """Test that turn_complete doesn't fire if no speech was detected."""
        mock_callback = Mock()
        detector = EOUDetector(
            session_id="test_session",
            on_turn_complete=mock_callback,
            silence_duration=0.1,
        )

        import struct
        import time

        # Process silence without prior speech
        silent_frame = struct.pack("<160h", *[0] * 160)
        detector._silence_start = time.monotonic() - 0.2
        # _had_speech is False by default

        detector.process_frame(silent_frame)

        # Should not fire because no speech was detected
        mock_callback.assert_not_called()

    def test_reset_clears_state(self):
        """Test that reset clears all state."""
        mock_callback = Mock()
        detector = EOUDetector(
            session_id="test_session",
            on_turn_complete=mock_callback,
        )

        # Set some state
        detector._had_speech = True
        detector._silence_start = 123.456
        detector._fired = True

        # Reset
        detector.reset()

        # Verify state is cleared
        assert detector._silence_start is None
        assert detector._had_speech is False
        assert detector._fired is False


class TestEOUThresholdMismatchFix:
    """Tests specifically for the EOU threshold mismatch fix.

    This verifies that the default changed from 0.8s to 1.0s
    and is configurable via skill pack.
    """

    def test_old_default_was_0_8_new_is_1_0(self):
        """Document the fix: old default was 0.8s, new is 1.0s."""
        mock_callback = Mock()
        detector = EOUDetector(
            session_id="test_session",
            on_turn_complete=mock_callback,
        )

        # The fix changed default from 0.8 to 1.0
        assert detector._silence_duration == 1.0
        assert detector._silence_duration != 0.8

    def test_skill_pack_can_override_to_1_5(self):
        """Test that skill pack can set threshold to 1.5s (as documented)."""
        mock_callback = Mock()

        # Simulate skill_pack with eou_threshold_seconds: 1.5
        skill_pack = {
            "agent": {
                "eou_threshold_seconds": 1.5
            }
        }

        eou_threshold = skill_pack.get("agent", {}).get("eou_threshold_seconds", 1.0)
        detector = EOUDetector(
            session_id="test_session",
            on_turn_complete=mock_callback,
            silence_duration=eou_threshold,
        )

        assert detector._silence_duration == 1.5

    def test_skill_pack_uses_default_when_not_specified(self):
        """Test that default is used when skill pack doesn't specify threshold."""
        mock_callback = Mock()

        # Skill pack without eou_threshold_seconds
        skill_pack = {
            "agent": {
                "name": "Test Agent"
                # No eou_threshold_seconds
            }
        }

        eou_threshold = skill_pack.get("agent", {}).get("eou_threshold_seconds", 1.0)
        detector = EOUDetector(
            session_id="test_session",
            on_turn_complete=mock_callback,
            silence_duration=eou_threshold,
        )

        assert detector._silence_duration == 1.0

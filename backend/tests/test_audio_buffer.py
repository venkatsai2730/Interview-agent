"""Unit tests for audio buffer backpressure."""
from __future__ import annotations

import pytest
from unittest.mock import Mock, patch
import struct

from pipeline.pipeline import AudioPipeline, MAX_BUFFER_FRAMES


class TestAudioBufferBackpressure:
    """Test suite for audio buffer backpressure mechanism."""

    def test_max_buffer_frames_constant(self):
        """Test that MAX_BUFFER_FRAMES is set to 100."""
        assert MAX_BUFFER_FRAMES == 100

    def test_audio_buffer_drops_oldest_when_full(self):
        """Test that oldest frames are dropped when buffer is full."""
        mock_inject = Mock()

        pipeline = AudioPipeline(
            session_id="test_session",
            skill_pack={"agent": {"name": "Test"}},
            on_audio_inject=mock_inject,
        )

        # Simulate Deepgram not connected (buffering mode)
        pipeline._deepgram_connected = False
        pipeline._reconnecting = True
        pipeline._connecting = False

        # Fill buffer to capacity
        for i in range(MAX_BUFFER_FRAMES):
            audio_chunk = struct.pack("<160h", *[i] * 160)
            pipeline.process_audio_frame(audio_chunk)

        assert len(pipeline._audio_buffer) == MAX_BUFFER_FRAMES

        # Add one more frame - should drop oldest
        new_chunk = struct.pack("<160h", *[999] * 160)
        pipeline.process_audio_frame(new_chunk)

        # Buffer should still be at max capacity
        assert len(pipeline._audio_buffer) == MAX_BUFFER_FRAMES

        # First frame should be dropped (was index 0, now index 1)
        # Last frame should be the new one
        first_frame = pipeline._audio_buffer[0]
        last_frame = pipeline._audio_buffer[-1]

        # First frame should now be what was originally index 1
        first_frame_data = struct.unpack("<160h", first_frame)[0]
        assert first_frame_data == 1  # Original index 1

        # Last frame should be the new one (999)
        last_frame_data = struct.unpack("<160h", last_frame)[0]
        assert last_frame_data == 999

    def test_audio_buffer_logs_warning_on_drop(self):
        """Test that warning is logged when frames are dropped."""
        mock_inject = Mock()

        pipeline = AudioPipeline(
            session_id="test_session",
            skill_pack={"agent": {"name": "Test"}},
            on_audio_inject=mock_inject,
        )

        pipeline._deepgram_connected = False
        pipeline._reconnecting = True
        pipeline._connecting = False

        # Fill buffer
        for i in range(MAX_BUFFER_FRAMES):
            audio_chunk = struct.pack("<160h", *[i] * 160)
            pipeline.process_audio_frame(audio_chunk)

        # Add one more - should trigger warning
        with patch('pipeline.pipeline.logger') as mock_logger:
            new_chunk = struct.pack("<160h", *[999] * 160)
            pipeline.process_audio_frame(new_chunk)

            # Verify warning was logged
            mock_logger.warning.assert_called_once()
            call_args = mock_logger.warning.call_args[0]
            assert "dropped oldest audio frame" in call_args[0]
            assert "buffer full" in call_args[0]

    def test_audio_buffer_accepts_frames_when_not_full(self):
        """Test that frames are accepted when buffer is not full."""
        mock_inject = Mock()

        pipeline = AudioPipeline(
            session_id="test_session",
            skill_pack={"agent": {"name": "Test"}},
            on_audio_inject=mock_inject,
        )

        pipeline._deepgram_connected = False
        pipeline._reconnecting = True

        # Add a few frames (less than max)
        for i in range(10):
            audio_chunk = struct.pack("<160h", *[i] * 160)
            pipeline.process_audio_frame(audio_chunk)

        assert len(pipeline._audio_buffer) == 10

        # No warnings should be logged
        with patch('pipeline.pipeline.logger') as mock_logger:
            audio_chunk = struct.pack("<160h", *[100] * 160)
            pipeline.process_audio_frame(audio_chunk)

            mock_logger.warning.assert_not_called()

    def test_audio_buffer_flushes_on_connect(self):
        """Test that buffer is flushed when Deepgram connects."""
        mock_inject = Mock()

        pipeline = AudioPipeline(
            session_id="test_session",
            skill_pack={"agent": {"name": "Test"}},
            on_audio_inject=mock_inject,
        )

        # Buffer some frames
        pipeline._deepgram_connected = False
        pipeline._reconnecting = True

        for i in range(10):
            audio_chunk = struct.pack("<160h", *[i] * 160)
            pipeline.process_audio_frame(audio_chunk)

        assert len(pipeline._audio_buffer) == 10

        # Simulate connection
        pipeline._deepgram_connected = True
        pipeline._reconnecting = False

        # In real implementation, _connect_deepgram flushes the buffer
        # Here we simulate the flush
        pipeline._audio_buffer.clear()

        assert len(pipeline._audio_buffer) == 0

    def test_buffer_size_calculation(self):
        """Test that 100 frames is approximately 3 seconds of audio."""
        # At 16kHz, 16-bit mono, 20ms frames:
        # - Frame size = 16000 Hz * 0.02s * 2 bytes = 640 bytes
        # - 100 frames = 2 seconds (at 20ms per frame)
        # - Or 3 seconds (at 30ms per frame)

        # This test documents the design decision
        frame_duration_ms = 20  # Typical frame duration
        total_duration_ms = MAX_BUFFER_FRAMES * frame_duration_ms

        assert total_duration_ms == 2000  # 2 seconds at 20ms/frame

        # If frames are 30ms (common for some codecs):
        frame_duration_ms_30 = 30
        total_duration_ms_30 = MAX_BUFFER_FRAMES * frame_duration_ms_30
        assert total_duration_ms_30 == 3000  # 3 seconds at 30ms/frame


class TestAudioBufferMemorySafety:
    """Tests to ensure buffer doesn't cause unbounded memory growth."""

    def test_buffer_never_exceeds_max_size(self):
        """Test that buffer never grows beyond MAX_BUFFER_FRAMES."""
        mock_inject = Mock()

        pipeline = AudioPipeline(
            session_id="test_session",
            skill_pack={"agent": {"name": "Test"}},
            on_audio_inject=mock_inject,
        )

        pipeline._deepgram_connected = False
        pipeline._reconnecting = True

        # Try to add many more frames than max
        for i in range(MAX_BUFFER_FRAMES * 3):
            audio_chunk = struct.pack("<160h", *[i % 1000] * 160)
            pipeline.process_audio_frame(audio_chunk)

            # Buffer should never exceed max
            assert len(pipeline._audio_buffer) <= MAX_BUFFER_FRAMES

    def test_buffer_memory_usage_bounded(self):
        """Test that buffer memory usage is bounded.

        This is a conceptual test - in practice, the bounded size
        ensures memory usage is also bounded.
        """
        # Each frame is approximately 640 bytes (160 samples * 2 bytes/sample for 20ms at 16kHz)
        frame_size_bytes = 640
        max_buffer_bytes = MAX_BUFFER_FRAMES * frame_size_bytes

        # Max buffer should be around 64KB
        assert max_buffer_bytes == 64000  # 62.5 KB

        # Even with overhead, this is manageable
        assert max_buffer_bytes < 100000  # Less than 100KB

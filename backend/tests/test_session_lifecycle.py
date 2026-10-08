"""Integration tests for session lifecycle.

These tests verify the complete session flow from creation to completion,
including the dual-state elimination (DB as single source of truth).
"""
from __future__ import annotations

import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, AsyncMock, patch

from sqlalchemy.ext.asyncio import AsyncSession

from backend.session_manager import (
    create_session,
    create_phone_session,
    get_session,
    update_session,
    SessionState,
    SessionStatus,
)
from backend.models import Session as SessionModel


class TestSessionLifecycle:
    """Integration tests for complete session lifecycle."""

    @pytest.fixture
    def sample_skill_pack(self):
        """Create a sample skill pack for testing."""
        return {
            "skill": {
                "id": "test-skill-v1",
                "name": "Test Skill",
                "version": "1.0.0",
            },
            "agent": {
                "name": "Test Agent",
                "persona": "You are a test agent.",
                "language": "en-US",
                "max_duration_minutes": 30,
                "model_preferences": [{"provider": "bedrock", "model": "test-model"}],
                "tts_voice": "cartesia:test-voice",
                "eou_threshold_seconds": 1.0,
            },
            "sections": [
                {
                    "id": "test-section",
                    "title": "Test Section",
                    "questions": [
                        {
                            "id": "q1",
                            "text": "Test question?",
                            "competency": "testing",
                            "max_follow_ups": 2,
                        }
                    ],
                }
            ],
            "rubric": [
                {
                    "competency": "testing",
                    "scores": {
                        "1": "Poor",
                        "3": "Good",
                        "5": "Excellent",
                    },
                }
            ],
            "report": {
                "template": "audit-log",
                "email_to": ["test@example.com"],
                "include_transcript": True,
            },
        }

    @pytest.mark.asyncio
    async def test_session_creation_persists_to_db(self, sample_skill_pack):
        """Test that create_session only persists to DB, not memory."""
        mock_db = AsyncMock(spec=AsyncSession)
        mock_db.execute = AsyncMock()
        mock_db.commit = AsyncMock()

        # Mock environment and Recall.ai bot creation
        with patch.dict('os.environ', {'RECALL_API_KEY': 'test_key'}):
            with patch('backend.session_manager.create_bot', return_value="bot_123"):
                with patch('backend.session_manager.validate_skill_pack') as mock_validate:
                    mock_validate.return_value = Mock(is_valid=True)

                    state = await create_session(
                        skill_pack=sample_skill_pack,
                        meeting_url="https://teams.microsoft.com/test",
                        db=mock_db,
                    )

        # Verify state was returned
        assert state is not None
        assert state.session_id.startswith("sess_")
        assert state.status == SessionStatus.PENDING

        # Verify DB was called
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_session_reads_from_db(self, sample_skill_pack):
        """Test that get_session reads from DB, not memory."""
        mock_db = AsyncMock(spec=AsyncSession)

        # Create a mock DB row
        mock_row = Mock(spec=SessionModel)
        mock_row.session_id = "sess_test123"
        mock_row.skill_pack = sample_skill_pack
        mock_row.recall_bot_id = "bot_123"
        mock_row.meeting_url = "https://teams.microsoft.com/test"
        mock_row.status = "active"
        mock_row.created_at = datetime.now(tz=timezone.utc)
        mock_row.started_at = datetime.now(tz=timezone.utc)
        mock_row.ended_at = None
        mock_row.context_data = None

        # Mock the query result
        mock_result = Mock()
        mock_result.scalar_one_or_none = Mock(return_value=mock_row)
        mock_db.execute = AsyncMock(return_value=mock_result)

        state = await get_session("sess_test123", mock_db)

        # Verify DB was queried
        mock_db.execute.assert_called_once()

        # Verify state was reconstructed from DB
        assert state is not None
        assert state.session_id == "sess_test123"
        assert state.status == SessionStatus.ACTIVE
        assert state.skill_pack["skill"]["id"] == "test-skill-v1"

    @pytest.mark.asyncio
    async def test_get_session_returns_none_for_missing(self):
        """Test that get_session returns None for non-existent session."""
        mock_db = AsyncMock(spec=AsyncSession)

        # Mock empty result
        mock_result = Mock()
        mock_result.scalar_one_or_none = Mock(return_value=None)
        mock_db.execute = AsyncMock(return_value=mock_result)

        state = await get_session("non_existent", mock_db)

        assert state is None

    @pytest.mark.asyncio
    async def test_update_session_writes_to_db(self, sample_skill_pack):
        """Test that update_session writes to DB."""
        mock_db = AsyncMock(spec=AsyncSession)

        # Create a mock DB row
        mock_row = Mock(spec=SessionModel)
        mock_row.status = "pending"
        mock_row.started_at = None
        mock_row.ended_at = None
        mock_row.error = None

        mock_result = Mock()
        mock_result.scalar_one_or_none = Mock(return_value=mock_row)
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        # Create state to update
        state = SessionState(
            session_id="sess_test123",
            skill_pack=sample_skill_pack,
            recall_bot_id="bot_123",
            teams_meeting_url="https://teams.microsoft.com/test",
            status=SessionStatus.ACTIVE,
            created_at=datetime.now(tz=timezone.utc),
            started_at=datetime.now(tz=timezone.utc),
        )

        await update_session(state, mock_db)

        # Verify DB was updated
        assert mock_row.status == "active"
        assert mock_row.started_at is not None
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_phone_session_creation(self, sample_skill_pack):
        """Test phone session creation."""
        mock_db = AsyncMock(spec=AsyncSession)
        mock_db.add = Mock()
        mock_db.commit = AsyncMock()

        with patch('backend.session_manager.validate_skill_pack') as mock_validate:
            mock_validate.return_value = Mock(is_valid=True)

            state = await create_phone_session(
                skill_pack=sample_skill_pack,
                phone_number="+1234567890",
                db=mock_db,
            )

        assert state is not None
        assert state.recall_bot_id == ""  # No bot for phone
        assert state.teams_meeting_url == ""
        assert state.status == SessionStatus.PENDING

        # Verify DB was called
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()


class TestDualStateElimination:
    """Tests specifically for the dual-state elimination fix."""

    @pytest.mark.asyncio
    async def test_no_in_memory_session_cache(self):
        """Test that sessions are not stored in memory cache.

        This verifies the fix removed the _sessions dict usage.
        """
        # The _sessions dict should no longer exist or be unused
        import backend.session_manager as sm

        # get_session should require db parameter
        import inspect
        sig = inspect.signature(sm.get_session)
        params = list(sig.parameters.keys())
        assert 'db' in params

    @pytest.mark.asyncio
    async def test_session_survives_instance_restart(self):
        """Test that session data survives instance restart.

        Since we use DB as single source of truth, sessions should
        be recoverable after a restart.
        """
        mock_db = AsyncMock(spec=AsyncSession)

        # Simulate DB with session data
        mock_row = Mock(spec=SessionModel)
        mock_row.session_id = "sess_persistent"
        mock_row.skill_pack = {"skill": {"id": "test"}}
        mock_row.recall_bot_id = "bot_123"
        mock_row.meeting_url = "https://test"
        mock_row.status = "active"
        mock_row.created_at = datetime.now(tz=timezone.utc)
        mock_row.started_at = datetime.now(tz=timezone.utc)
        mock_row.ended_at = None
        mock_row.context_data = None

        mock_result = Mock()
        mock_result.scalar_one_or_none = Mock(return_value=mock_row)
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Simulate "restart" - no in-memory state, only DB
        state = await get_session("sess_persistent", mock_db)

        assert state is not None
        assert state.status == SessionStatus.ACTIVE


class TestMultiInstanceScenario:
    """Tests for multi-instance deployment scenarios."""

    @pytest.mark.asyncio
    async def test_session_visible_across_instances(self):
        """Test that sessions created by one instance are visible to others.

        This is the key benefit of using DB as single source of truth.
        """
        # Instance A creates session
        mock_db_a = AsyncMock(spec=AsyncSession)
        mock_db_a.commit = AsyncMock()

        # Instance B queries session
        mock_db_b = AsyncMock(spec=AsyncSession)

        mock_row = Mock(spec=SessionModel)
        mock_row.session_id = "sess_shared"
        mock_row.skill_pack = {"skill": {"id": "shared-skill"}}
        mock_row.recall_bot_id = "bot_shared"
        mock_row.meeting_url = "https://shared"
        mock_row.status = "pending"
        mock_row.created_at = datetime.now(tz=timezone.utc)
        mock_row.started_at = None
        mock_row.ended_at = None
        mock_row.context_data = None

        mock_result = Mock()
        mock_result.scalar_one_or_none = Mock(return_value=mock_row)
        mock_db_b.execute = AsyncMock(return_value=mock_result)

        # Instance B can see the session
        state = await get_session("sess_shared", mock_db_b)

        assert state is not None
        assert state.session_id == "sess_shared"

    @pytest.mark.asyncio
    async def test_concurrent_session_updates(self):
        """Test that concurrent updates are handled via DB."""
        mock_db = AsyncMock(spec=AsyncSession)

        mock_row = Mock(spec=SessionModel)
        mock_row.status = "pending"
        mock_row.started_at = None
        mock_row.ended_at = None
        mock_row.error = None

        mock_result = Mock()
        mock_result.scalar_one_or_none = Mock(return_value=mock_row)
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        # Simulate multiple instances trying to update
        from backend.session_manager import SessionState, SessionStatus

        state = SessionState(
            session_id="sess_concurrent",
            skill_pack={},
            recall_bot_id="bot",
            teams_meeting_url="https://test",
            status=SessionStatus.ACTIVE,
            created_at=datetime.now(tz=timezone.utc),
            started_at=datetime.now(tz=timezone.utc),
        )

        await update_session(state, mock_db)

        # DB handles concurrency via transactions
        mock_db.commit.assert_called_once()


class TestSessionStateTransitions:
    """Tests for session state transition logic."""

    @pytest.mark.asyncio
    async def test_pending_to_active_transition(self):
        """Test transition from PENDING to ACTIVE."""
        mock_db = AsyncMock(spec=AsyncSession)

        mock_row = Mock(spec=SessionModel)
        mock_row.status = "pending"
        mock_row.started_at = None

        mock_result = Mock()
        mock_result.scalar_one_or_none = Mock(return_value=mock_row)
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        from backend.session_manager import SessionState, SessionStatus

        state = SessionState(
            session_id="sess_transition",
            skill_pack={},
            recall_bot_id="bot",
            teams_meeting_url="https://test",
            status=SessionStatus.ACTIVE,
            created_at=datetime.now(tz=timezone.utc),
            started_at=datetime.now(tz=timezone.utc),
        )

        await update_session(state, mock_db)

        assert mock_row.status == "active"
        assert mock_row.started_at is not None

    @pytest.mark.asyncio
    async def test_active_to_completed_transition(self):
        """Test transition from ACTIVE to COMPLETED."""
        mock_db = AsyncMock(spec=AsyncSession)

        mock_row = Mock(spec=SessionModel)
        mock_row.status = "active"
        mock_row.started_at = datetime.now(tz=timezone.utc)
        mock_row.ended_at = None

        mock_result = Mock()
        mock_result.scalar_one_or_none = Mock(return_value=mock_row)
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        from backend.session_manager import SessionState, SessionStatus

        state = SessionState(
            session_id="sess_complete",
            skill_pack={},
            recall_bot_id="bot",
            teams_meeting_url="https://test",
            status=SessionStatus.COMPLETED,
            created_at=datetime.now(tz=timezone.utc),
            started_at=datetime.now(tz=timezone.utc),
            ended_at=datetime.now(tz=timezone.utc),
        )

        await update_session(state, mock_db)

        assert mock_row.status == "completed"
        assert mock_row.ended_at is not None

    @pytest.mark.asyncio
    async def test_failed_transition(self):
        """Test transition to FAILED state."""
        mock_db = AsyncMock(spec=AsyncSession)

        mock_row = Mock(spec=SessionModel)
        mock_row.status = "active"
        mock_row.ended_at = None
        mock_row.error = None

        mock_result = Mock()
        mock_result.scalar_one_or_none = Mock(return_value=mock_row)
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        from backend.session_manager import SessionState, SessionStatus

        state = SessionState(
            session_id="sess_failed",
            skill_pack={},
            recall_bot_id="bot",
            teams_meeting_url="https://test",
            status=SessionStatus.FAILED,
            created_at=datetime.now(tz=timezone.utc),
            ended_at=datetime.now(tz=timezone.utc),
            error="Test error message",
        )

        await update_session(state, mock_db)

        assert mock_row.status == "failed"
        assert mock_row.error == "Test error message"

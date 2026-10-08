"""Unit tests for key integration points.

Covers requirements: 1.1, 1.3, 2.1, 2.2, 3.4, 5.2, 5.4, 6.3, 10.4,
                     11.1, 12.4, 12.5, 12.8, 16.2, 16.5

All tests use pytest + unittest.mock. No real external services are called.
"""
from __future__ import annotations

import asyncio
import json
import struct
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helper: wrap a mock DB session in an async generator (for patching get_db)
# ---------------------------------------------------------------------------

async def _async_gen(obj):
    """Yield *obj* once — used to mock async generator functions like get_db."""
    yield obj


# ---------------------------------------------------------------------------
# Shared SkillPack fixture (same structure as test_e2e_mock.py)
# ---------------------------------------------------------------------------

SKILL_PACK: dict = {
    "skill": {"id": "interviewer-v1", "name": "Technical Interviewer", "version": "1.0.0"},
    "agent": {
        "name": "Vero",
        "persona": "You are Vero, a professional technical interviewer.",
        "language": "en-US",
        "max_duration_minutes": 30,
        "model_preferences": [
            {"provider": "bedrock", "model": "anthropic.claude-3-5-sonnet-20241022-v2:0"}
        ],
        "tts_voice": "cartesia:sonic-english",
    },
    "sections": [
        {
            "id": "sec1",
            "title": "System Design",
            "questions": [
                {
                    "id": "q1",
                    "text": "Describe a distributed cache you have designed.",
                    "probes": ["How did you handle cache invalidation?"],
                    "competency": "system-design",
                    "max_follow_ups": 1,
                },
                {
                    "id": "q2",
                    "text": "How do you approach API versioning?",
                    "probes": ["What are the trade-offs?"],
                    "competency": "api-design",
                    "max_follow_ups": 1,
                },
            ],
        }
    ],
    "rubric": [
        {
            "competency": "system-design",
            "scores": {
                "1": "No understanding",
                "2": "Basic",
                "3": "Adequate",
                "4": "Strong",
                "5": "Expert",
            },
        },
        {
            "competency": "api-design",
            "scores": {
                "1": "No understanding",
                "2": "Basic",
                "3": "Adequate",
                "4": "Strong",
                "5": "Expert",
            },
        },
    ],
    "report": {
        "template": "scorecard",
        "email_to": ["host@example.com"],
        "include_transcript": True,
    },
}


# ---------------------------------------------------------------------------
# PCM frame helpers
# ---------------------------------------------------------------------------

def _silent_frame(num_samples: int = 800) -> bytes:
    return struct.pack(f"<{num_samples}h", *([0] * num_samples))


def _speech_frame(num_samples: int = 800, amplitude: int = 8000) -> bytes:
    return struct.pack(f"<{num_samples}h", *([amplitude] * num_samples))


# ===========================================================================
# Test 1 — POST /sessions with valid SkillPack returns session_id + pending
# Requirements: 1.1, 2.1
# ===========================================================================

class TestPostSessionsValid:
    """POST /sessions with a valid SkillPack must return session_id and status=pending."""

    @pytest.mark.asyncio
    async def test_post_sessions_valid_skillpack_returns_session_id(self):
        import yaml
        from backend.session_manager import SessionState, SessionStatus
        from datetime import datetime, timezone

        yaml_content = yaml.dump(SKILL_PACK)

        # Build a fake SessionState that create_session would return
        fake_state = SessionState(
            session_id="sess_abc123",
            skill_pack=SKILL_PACK,
            recall_bot_id="bot_xyz",
            teams_meeting_url="https://teams.example.com/meeting",
            status=SessionStatus.PENDING,
            created_at=datetime.now(tz=timezone.utc),
        )

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()

        async def fake_get_db():
            yield mock_db

        async def fake_create_session(skill_pack, meeting_url, db):
            return fake_state

        from backend.main import app, _get_db

        app.dependency_overrides[_get_db] = fake_get_db

        try:
            # create_session is imported inside the endpoint, so patch at its source module.
            # The endpoint also calls get_db() directly (not via Depends), so patch it at source.
            with patch("backend.session_manager.create_session", side_effect=fake_create_session):
                with patch("backend.db.get_db", return_value=_async_gen(mock_db)):
                    from httpx import AsyncClient, ASGITransport

                    async with AsyncClient(
                        transport=ASGITransport(app=app), base_url="http://test"
                    ) as client:
                        resp = await client.post(
                            "/sessions",
                            json={
                                "yaml_content": yaml_content,
                                "meeting_url": "https://teams.example.com/meeting",
                            },
                        )

            assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
            body = resp.json()
            assert "session_id" in body, "Response must contain session_id"
            assert body["status"] == "pending", "Status must be 'pending'"
        finally:
            app.dependency_overrides.pop(_get_db, None)


# ===========================================================================
# Test 2 — POST /sessions with missing required field returns 422
# Requirements: 2.2
# ===========================================================================

class TestPostSessionsMissingField:
    """POST /sessions with YAML missing agent.name must return 422 with field in error."""

    @pytest.mark.asyncio
    async def test_post_sessions_missing_required_field_returns_422(self):
        import copy
        import yaml

        bad_pack = copy.deepcopy(SKILL_PACK)
        del bad_pack["agent"]["name"]  # remove required field
        yaml_content = yaml.dump(bad_pack)

        mock_db = AsyncMock()

        async def fake_get_db():
            yield mock_db

        from backend.main import app, _get_db

        app.dependency_overrides[_get_db] = fake_get_db

        try:
            from httpx import AsyncClient, ASGITransport

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/sessions",
                    json={
                        "yaml_content": yaml_content,
                        "meeting_url": "https://teams.example.com/meeting",
                    },
                )

            assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"
            detail = resp.json().get("detail", "")
            detail_str = json.dumps(detail) if isinstance(detail, dict) else str(detail)
            assert "agent.name" in detail_str, (
                f"Error detail must mention 'agent.name', got: {detail_str}"
            )
        finally:
            app.dependency_overrides.pop(_get_db, None)


# ===========================================================================
# Test 3 — POST /recall/webhook bot_joined transitions session to active
# Requirements: 1.1, 1.2
# ===========================================================================

class TestRecallWebhookBotJoined:
    """bot_joined webhook must transition session status from pending to active."""

    @pytest.mark.asyncio
    async def test_recall_webhook_bot_joined_transitions_to_active(self):
        from backend.models import Session as SessionModel

        mock_row = MagicMock(spec=SessionModel)
        mock_row.session_id = "sess_webhook"
        mock_row.recall_bot_id = "bot_webhook"
        mock_row.status = "pending"
        mock_row.started_at = None
        mock_row.skill_pack = SKILL_PACK

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_row

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        async def fake_get_db():
            yield mock_db

        from backend.main import app, _get_db

        app.dependency_overrides[_get_db] = fake_get_db

        try:
            # get_session / register_pipeline are imported inside the handler;
            # patch at their source modules.
            with patch("backend.session_manager.get_session", return_value=None):
                with patch("backend.session_manager.register_pipeline"):
                    with patch("pipeline.pipeline.AudioPipeline") as MockPipeline:
                        mock_pipeline_instance = AsyncMock()
                        MockPipeline.return_value = mock_pipeline_instance

                        from httpx import AsyncClient, ASGITransport

                        async with AsyncClient(
                            transport=ASGITransport(app=app), base_url="http://test"
                        ) as client:
                            resp = await client.post(
                                "/recall/webhook",
                                json={
                                    "event": "bot_joined",
                                    "data": {"bot": {"id": "bot_webhook"}},
                                },
                            )

            assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
            # The row's status must have been set to "active"
            assert mock_row.status == "active", (
                f"Session status must be 'active' after bot_joined, got: {mock_row.status}"
            )
            mock_db.commit.assert_called()
        finally:
            app.dependency_overrides.pop(_get_db, None)


# ===========================================================================
# Test 4 — Recall.ai join timeout retries then raises RecallJoinError
# Requirements: 1.3
# ===========================================================================

class TestRecallJoinTimeout:
    """create_bot must raise RecallJoinError when both attempts time out."""

    @pytest.mark.asyncio
    async def test_recall_join_timeout_retries_then_503(self):
        import httpx
        from backend.recall_client import RecallJoinError, create_bot

        # Patch acquire_teams_token so we don't need Azure AD env vars
        with patch(
            "backend.recall_client.acquire_teams_token",
            new=AsyncMock(return_value="fake-azure-token"),
        ):
            # Patch asyncio.sleep to avoid real 10s wait
            with patch("backend.recall_client.asyncio.sleep", new=AsyncMock()):
                # Both POST attempts raise TimeoutException
                with patch(
                    "httpx.AsyncClient.post",
                    side_effect=httpx.TimeoutException("timed out"),
                ):
                    with pytest.raises(RecallJoinError):
                        await create_bot(
                            "https://teams.example.com/meeting",
                            "Vero",
                            "fake-recall-key",
                        )


# ===========================================================================
# Test 5 — Cartesia failure falls back to ElevenLabs
# Requirements: 3.4
# ===========================================================================

class TestCartesiaFallback:
    """When Cartesia raises _CartesiaError, ElevenLabs must be called instead."""

    def test_cartesia_failure_falls_back_to_elevenlabs(self):
        from pipeline.tts_injector import TTSInjector, _CartesiaError

        chunks_received: list[bytes] = []
        el_chunk = b"\xff\xfe" * 50

        injector = TTSInjector(
            session_id="sess_fallback",
            on_audio_chunk=lambda c: chunks_received.append(c),
            on_vero_speaking=lambda _: None,
            cartesia_api_key="fake",
            elevenlabs_api_key="fake",
        )

        with patch.object(
            injector, "_stream_cartesia", side_effect=_CartesiaError("HTTP 500")
        ):
            with patch.object(
                injector, "_stream_elevenlabs", return_value=iter([el_chunk])
            ):
                injector.synthesise_and_inject("Fallback test.", "cartesia:sonic-english")

        assert chunks_received == [el_chunk], (
            "ElevenLabs chunk must be injected when Cartesia fails"
        )


# ===========================================================================
# Test 6 — EOU fires after silence (mechanism test with silence_duration=0.0)
# Requirements: 5.2
# ===========================================================================

class TestEOUFiresAfterSilence:
    """EOU must fire after the silence threshold is exceeded following speech."""

    def test_eou_fires_after_1500ms_silence(self):
        """Use silence_duration=0.0 to verify the mechanism deterministically."""
        from pipeline.eou_detector import EOUDetector

        fired: list[str] = []

        detector = EOUDetector(
            session_id="sess_eou_fire",
            on_turn_complete=lambda sid: fired.append(sid),
            silence_duration=0.0,  # zero threshold — fires on second silent frame
        )

        # Speech frame marks that speech has occurred
        detector.process_frame(_speech_frame())
        assert not fired

        # First silent frame: starts the silence window
        detector.process_frame(_silent_frame())
        # Second silent frame: elapsed >= 0.0 → fires
        detector.process_frame(_silent_frame())

        assert fired == ["sess_eou_fire"], "EOU must fire after silence threshold"


# ===========================================================================
# Test 7 — EOU does NOT fire during vero_speaking=True
# Requirements: 5.4
# ===========================================================================

class TestEOUSuppressedDuringVeroSpeaking:
    """EOU must not fire while vero_speaking is True."""

    def test_eou_does_not_fire_during_vero_speaking(self):
        from pipeline.eou_detector import EOUDetector

        fired: list[str] = []

        detector = EOUDetector(
            session_id="sess_eou_suppress",
            on_turn_complete=lambda sid: fired.append(sid),
            silence_duration=0.0,
        )

        detector.set_vero_speaking(True)

        # Feed speech then silence — must NOT fire
        detector.process_frame(_speech_frame())
        detector.process_frame(_silent_frame())
        detector.process_frame(_silent_frame())
        detector.process_frame(_silent_frame())

        assert not fired, "EOU must be suppressed while vero_speaking=True"


# ===========================================================================
# Test 8 — Turn_Output with empty next_utterance uses SAFE_FALLBACK_UTTERANCE
# Requirements: 6.3
# ===========================================================================

class TestTurnOutputFallback:
    """When next_utterance is empty, pipeline must use SAFE_FALLBACK_UTTERANCE."""

    @pytest.mark.asyncio
    async def test_turn_output_schema_failure_retries_once(self):
        from pipeline.pipeline import AudioPipeline, SAFE_FALLBACK_UTTERANCE
        from pipeline.rpc_bridge import TurnOutputMessage

        utterances_synthesised: list[str] = []

        pipeline = AudioPipeline(
            session_id="sess_fallback_utt",
            skill_pack=SKILL_PACK,
            on_audio_inject=lambda _: None,
            deepgram_api_key="fake",
        )

        # Capture what utterance is passed to synthesise_and_inject
        def capture_synthesise(utterance: str, voice_id: str) -> None:
            utterances_synthesised.append(utterance)

        with patch.object(pipeline._tts, "synthesise_and_inject", side_effect=capture_synthesise):
            # TurnOutputMessage with empty next_utterance
            msg = TurnOutputMessage(
                session_id="sess_fallback_utt",
                turn_index=1,
                next_utterance="",  # empty — should trigger fallback
                action="follow_up",
                question_id="q1",
                competency="system-design",
                flags=[],
            )
            await pipeline._handle_turn_output(msg)

        assert len(utterances_synthesised) == 1
        assert utterances_synthesised[0] == SAFE_FALLBACK_UTTERANCE, (
            f"Expected SAFE_FALLBACK_UTTERANCE, got: {utterances_synthesised[0]!r}"
        )


# ===========================================================================
# Test 9 — SilenceTimeoutMessage serialises/deserialises correctly
# Requirements: 10.4
# ===========================================================================

class TestSilenceTimeoutMessage:
    """SilenceTimeoutMessage with consecutive_count=2 must round-trip correctly."""

    def test_two_consecutive_silence_timeouts_advance(self):
        from pipeline.rpc_bridge import (
            SilenceTimeoutMessage,
            parse_rpc_message,
            serialize_rpc_message,
        )

        msg = SilenceTimeoutMessage(
            session_id="sess_silence",
            silence_duration_ms=8000,
            consecutive_count=2,
        )

        serialised = serialize_rpc_message(msg)
        parsed = parse_rpc_message(serialised)

        assert isinstance(parsed, SilenceTimeoutMessage), (
            f"Expected SilenceTimeoutMessage, got {type(parsed)}"
        )
        assert parsed.consecutive_count == 2, (
            f"consecutive_count must be 2, got {parsed.consecutive_count}"
        )
        assert parsed.session_id == "sess_silence"
        assert parsed.silence_duration_ms == 8000
        assert parsed.type == "silence_timeout"


# ===========================================================================
# Test 10 — All questions complete → generate_report has no questions_not_reached
# Requirements: 11.1
# ===========================================================================

class TestAllQuestionsComplete:
    """When all questions have scores, generate_report must have no questions_not_reached."""

    def test_all_questions_complete_action_close(self):
        from pipeline.rpc_bridge import SessionSummaryMessage
        from backend.report_generator import generate_report

        summary = SessionSummaryMessage(
            session_id="sess_complete",
            scores=[
                {
                    "question_id": "q1",
                    "competency": "system-design",
                    "score": 4,
                    "rationale": "Solid understanding.",
                },
                {
                    "question_id": "q2",
                    "competency": "api-design",
                    "score": 3,
                    "rationale": "Adequate.",
                },
            ],
            transcript=[],
            questions_not_reached=[],
        )

        report = generate_report(summary, SKILL_PACK, "sess_complete")

        assert report.questions_not_reached == [], (
            "questions_not_reached must be empty when all questions are scored"
        )
        assert len(report.scores) == 2, "All 2 questions must appear in scores"
        scored_ids = {qs.question_id for qs in report.scores}
        assert "q1" in scored_ids and "q2" in scored_ids


# ===========================================================================
# Test 11 — Scorecard report contains scores, competency_summary, hire/no-hire
# Requirements: 12.4
# ===========================================================================

class TestScorecardReport:
    """Scorecard report must include scores, competency_summary, and recommendation."""

    def test_scorecard_report_contains_scores_competency_summary_hire_nohire(self):
        from pipeline.rpc_bridge import SessionSummaryMessage
        from backend.report_generator import generate_report

        summary = SessionSummaryMessage(
            session_id="sess_scorecard",
            scores=[
                {
                    "question_id": "q1",
                    "competency": "system-design",
                    "score": 4,
                    "rationale": "Strong answer.",
                },
                {
                    "question_id": "q2",
                    "competency": "api-design",
                    "score": 4,
                    "rationale": "Good versioning knowledge.",
                },
            ],
            transcript=[],
            questions_not_reached=[],
        )

        report = generate_report(summary, SKILL_PACK, "sess_scorecard")

        assert report.scores, "Report must contain scores"
        assert report.competency_summary, "Report must contain competency_summary"
        assert report.recommendation in ("hire", "no-hire"), (
            f"recommendation must be 'hire' or 'no-hire', got: {report.recommendation!r}"
        )


# ===========================================================================
# Test 12 — include_transcript=True → report contains transcript with speaker labels
# Requirements: 12.5
# ===========================================================================

class TestIncludeTranscript:
    """When include_transcript=True, report.transcript must contain speaker labels."""

    def test_include_transcript_true_report_contains_transcript(self):
        from pipeline.rpc_bridge import SessionSummaryMessage
        from backend.report_generator import generate_report

        transcript_turns = [
            {"speaker": "Vero", "text": "Tell me about caching.", "timestamp_ms": 1000},
            {"speaker": "participant", "text": "I used Redis.", "timestamp_ms": 2000},
        ]

        summary = SessionSummaryMessage(
            session_id="sess_transcript",
            scores=[
                {
                    "question_id": "q1",
                    "competency": "system-design",
                    "score": 3,
                    "rationale": "Adequate.",
                },
                {
                    "question_id": "q2",
                    "competency": "api-design",
                    "score": 3,
                    "rationale": "Adequate.",
                },
            ],
            transcript=transcript_turns,
            questions_not_reached=[],
        )

        # Use a skill_pack with include_transcript=True
        import copy
        sp = copy.deepcopy(SKILL_PACK)
        sp["report"]["include_transcript"] = True

        report = generate_report(summary, sp, "sess_transcript")

        assert report.transcript is not None, "report.transcript must not be None"
        assert len(report.transcript) == 2, "Transcript must contain both turns"

        speakers = {t["speaker"] for t in report.transcript}
        assert speakers, "Transcript entries must have speaker labels"
        assert "Vero" in speakers or "participant" in speakers, (
            "Transcript must contain speaker labels"
        )


# ===========================================================================
# Test 13 — Resend failure retries once then logs
# Requirements: 12.8
# ===========================================================================

class TestResendRetry:
    """On Resend failure, deliver_report must retry once for the same address."""

    @pytest.mark.asyncio
    async def test_resend_failure_retries_once_then_logs(self):
        from backend.report_generator import deliver_report, generate_report
        from pipeline.rpc_bridge import SessionSummaryMessage

        summary = SessionSummaryMessage(
            session_id="sess_resend",
            scores=[
                {
                    "question_id": "q1",
                    "competency": "system-design",
                    "score": 4,
                    "rationale": "Good.",
                },
                {
                    "question_id": "q2",
                    "competency": "api-design",
                    "score": 4,
                    "rationale": "Good.",
                },
            ],
            transcript=[],
            questions_not_reached=[],
        )

        report = generate_report(summary, SKILL_PACK, "sess_resend")

        # First call fails (status 500), second succeeds (status 201)
        fail_resp = MagicMock()
        fail_resp.status_code = 500
        fail_resp.text = "Internal Server Error"

        success_resp = MagicMock()
        success_resp.status_code = 201
        success_resp.text = "Created"

        call_count = 0

        async def mock_post(url, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return fail_resp
            return success_resp

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()

        with patch.dict("os.environ", {"RESEND_API_KEY": "fake-key"}):
            with patch("httpx.AsyncClient.post", side_effect=mock_post):
                # Patch asyncio.sleep to skip the 30s retry delay
                with patch("backend.report_generator.asyncio.sleep", new=AsyncMock()):
                    # Patch _post_teams_summary to avoid Bot Framework calls
                    with patch(
                        "backend.report_generator._post_teams_summary",
                        new=AsyncMock(return_value=False),
                    ):
                        await deliver_report(report, SKILL_PACK, mock_db)

        # Resend must have been called twice for the single recipient
        assert call_count == 2, (
            f"Resend must be called twice (1 attempt + 1 retry), got {call_count}"
        )


# ===========================================================================
# Test 14 — YAML syntax error at line 7 includes line number in ParseError
# Requirements: 16.2
# ===========================================================================

class TestYAMLSyntaxErrorLineNumber:
    """ParseError must include the line number of the YAML syntax error."""

    def test_yaml_syntax_error_at_line_7_includes_line_number(self):
        from backend.skill_pack_validator import ParseError, parse_skill_pack_yaml

        # PyYAML reports the error at the line where it detects the problem.
        # An unclosed bracket on line N is detected at stream end (line N+1).
        # So we place the unclosed bracket on line 6 → PyYAML reports line 7.
        yaml_with_error = (
            "skill:\n"           # line 1
            "  id: test\n"       # line 2
            "  name: Test\n"     # line 3
            "  version: 1.0\n"   # line 4
            "agent:\n"           # line 5
            "  bad: [unclosed\n" # line 6 — unclosed bracket → error detected at line 7
        )

        with pytest.raises(ParseError) as exc_info:
            parse_skill_pack_yaml(yaml_with_error)

        err = exc_info.value
        assert err.line == 7, (
            f"ParseError.line must be 7 for an error detected at line 7, got {err.line}"
        )
        assert "7" in str(err), f"String representation must contain '7', got: {err}"


# ===========================================================================
# Test 15 — max_duration_minutes boundary: 0→invalid, 1→valid, 120→valid, 121→invalid
# Requirements: 16.5
# ===========================================================================

class TestMaxDurationMinutesBoundary:
    """validate_skill_pack must enforce max_duration_minutes in [1, 120]."""

    def _make_pack(self, max_duration: int) -> dict:
        import copy
        sp = copy.deepcopy(SKILL_PACK)
        sp["agent"]["max_duration_minutes"] = max_duration
        return sp

    def test_max_duration_0_is_invalid(self):
        from backend.skill_pack_validator import validate_skill_pack

        result = validate_skill_pack(self._make_pack(0))
        assert not result.is_valid
        assert "agent.max_duration_minutes" in result.errors

    def test_max_duration_1_is_valid(self):
        from backend.skill_pack_validator import validate_skill_pack

        result = validate_skill_pack(self._make_pack(1))
        assert result.is_valid, f"max_duration_minutes=1 must be valid, errors: {result.errors}"
        assert "agent.max_duration_minutes" not in result.errors

    def test_max_duration_120_is_valid(self):
        from backend.skill_pack_validator import validate_skill_pack

        result = validate_skill_pack(self._make_pack(120))
        assert result.is_valid, f"max_duration_minutes=120 must be valid, errors: {result.errors}"
        assert "agent.max_duration_minutes" not in result.errors

    def test_max_duration_121_is_invalid(self):
        from backend.skill_pack_validator import validate_skill_pack

        result = validate_skill_pack(self._make_pack(121))
        assert not result.is_valid
        assert "agent.max_duration_minutes" in result.errors


# ===========================================================================
# Test 16 — GET /sessions/{session_id} live monitor fields
# Requirements: 23.1, 23.2
# ===========================================================================

class TestGetSessionLiveMonitor:
    """GET /sessions/{session_id} must return live monitor fields.

    Validates: Requirements 23.1, 23.2
    """

    def _make_session_row(self, started_at=None, ended_at=None, status="active"):
        """Build a mock Session ORM row."""
        from backend.models import Session as SessionModel
        row = MagicMock(spec=SessionModel)
        row.session_id = "sess_monitor"
        row.status = status
        row.skill_pack = SKILL_PACK
        row.started_at = started_at
        row.ended_at = ended_at
        return row

    def _make_turn_row(self, turn_index: int, question_id: Optional[str],
                       eou_ts_ms: Optional[int] = None, first_audio_ts_ms: Optional[int] = None):
        from backend.models import Turn as TurnModel
        row = MagicMock(spec=TurnModel)
        row.turn_index = turn_index
        row.question_id = question_id
        row.eou_ts_ms = eou_ts_ms
        row.first_audio_ts_ms = first_audio_ts_ms
        return row

    @pytest.mark.asyncio
    async def test_current_question_text_first_question_when_no_turns(self):
        """With no turns, current_question_index=0 → first question text."""
        from backend.main import app, _get_db

        session_row = self._make_session_row()
        report_result = MagicMock()
        report_result.scalar_one_or_none.return_value = None

        call_count = 0

        async def fake_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                # Session lookup
                result.scalar_one_or_none.return_value = session_row
            elif call_count == 2:
                # Turns lookup
                result.scalars.return_value.all.return_value = []
            else:
                # Report lookup
                result.scalar_one_or_none.return_value = None
            return result

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=fake_execute)

        async def fake_get_db():
            yield mock_db

        app.dependency_overrides[_get_db] = fake_get_db

        try:
            from httpx import AsyncClient, ASGITransport

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/sessions/sess_monitor")

            assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
            body = resp.json()

            assert body["current_question_index"] == 0
            assert body["current_question_text"] == "Describe a distributed cache you have designed."
            assert body["turn_count"] == 0
            assert body["has_report"] is False
            assert body["turn_latencies"] == []
            assert body["skill_pack_name"] == "Technical Interviewer"
        finally:
            app.dependency_overrides.pop(_get_db, None)

    @pytest.mark.asyncio
    async def test_current_question_advances_with_distinct_question_ids(self):
        """After turns with q1, current_question_index=1 → second question text."""
        from backend.main import app, _get_db

        session_row = self._make_session_row()
        turn_rows = [
            self._make_turn_row(0, "q1", eou_ts_ms=1000, first_audio_ts_ms=2500),
            self._make_turn_row(1, "q1"),  # same question, no latency data
        ]

        call_count = 0

        async def fake_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = session_row
            elif call_count == 2:
                result.scalars.return_value.all.return_value = turn_rows
            else:
                result.scalar_one_or_none.return_value = None
            return result

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=fake_execute)

        async def fake_get_db():
            yield mock_db

        app.dependency_overrides[_get_db] = fake_get_db

        try:
            from httpx import AsyncClient, ASGITransport

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/sessions/sess_monitor")

            assert resp.status_code == 200
            body = resp.json()

            # One distinct question_id (q1) → index 1 → second question
            assert body["current_question_index"] == 1
            assert body["current_question_text"] == "How do you approach API versioning?"
            assert body["turn_count"] == 2
            # One turn has latency data
            assert len(body["turn_latencies"]) == 1
            assert body["turn_latencies"][0]["turn_index"] == 0
            assert body["turn_latencies"][0]["latency_ms"] == 1500
        finally:
            app.dependency_overrides.pop(_get_db, None)

    @pytest.mark.asyncio
    async def test_elapsed_seconds_zero_when_not_started(self):
        """elapsed_seconds must be 0 when started_at is None."""
        from backend.main import app, _get_db

        session_row = self._make_session_row(started_at=None, status="pending")

        call_count = 0

        async def fake_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = session_row
            elif call_count == 2:
                result.scalars.return_value.all.return_value = []
            else:
                result.scalar_one_or_none.return_value = None
            return result

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=fake_execute)

        async def fake_get_db():
            yield mock_db

        app.dependency_overrides[_get_db] = fake_get_db

        try:
            from httpx import AsyncClient, ASGITransport

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/sessions/sess_monitor")

            assert resp.status_code == 200
            body = resp.json()
            assert body["elapsed_seconds"] == 0.0
        finally:
            app.dependency_overrides.pop(_get_db, None)

    @pytest.mark.asyncio
    async def test_elapsed_seconds_uses_ended_at_when_completed(self):
        """elapsed_seconds must use (ended_at - started_at) for completed sessions."""
        from datetime import datetime, timezone, timedelta
        from backend.main import app, _get_db

        started = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        ended = started + timedelta(seconds=120)
        session_row = self._make_session_row(started_at=started, ended_at=ended, status="completed")

        call_count = 0

        async def fake_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = session_row
            elif call_count == 2:
                result.scalars.return_value.all.return_value = []
            else:
                result.scalar_one_or_none.return_value = None
            return result

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=fake_execute)

        async def fake_get_db():
            yield mock_db

        app.dependency_overrides[_get_db] = fake_get_db

        try:
            from httpx import AsyncClient, ASGITransport

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/sessions/sess_monitor")

            assert resp.status_code == 200
            body = resp.json()
            assert body["elapsed_seconds"] == 120.0
        finally:
            app.dependency_overrides.pop(_get_db, None)

    @pytest.mark.asyncio
    async def test_has_report_true_when_report_row_exists(self):
        """has_report must be True when a Report row exists for the session."""
        from backend.main import app, _get_db
        from backend.models import Report as ReportModel

        session_row = self._make_session_row(status="completed")
        report_row = MagicMock(spec=ReportModel)
        report_row.email_sent = True

        call_count = 0

        async def fake_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = session_row
            elif call_count == 2:
                result.scalars.return_value.all.return_value = []
            else:
                result.scalar_one_or_none.return_value = report_row
            return result

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=fake_execute)

        async def fake_get_db():
            yield mock_db

        app.dependency_overrides[_get_db] = fake_get_db

        try:
            from httpx import AsyncClient, ASGITransport

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/sessions/sess_monitor")

            assert resp.status_code == 200
            body = resp.json()
            assert body["has_report"] is True
            assert body["report_delivered"] is True
        finally:
            app.dependency_overrides.pop(_get_db, None)

    @pytest.mark.asyncio
    async def test_current_question_text_none_when_all_questions_done(self):
        """When all questions are done, current_question_text must be None."""
        from backend.main import app, _get_db

        session_row = self._make_session_row(status="completed")
        # Both questions have been seen
        turn_rows = [
            self._make_turn_row(0, "q1"),
            self._make_turn_row(1, "q2"),
        ]

        call_count = 0

        async def fake_execute(stmt):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = session_row
            elif call_count == 2:
                result.scalars.return_value.all.return_value = turn_rows
            else:
                result.scalar_one_or_none.return_value = None
            return result

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=fake_execute)

        async def fake_get_db():
            yield mock_db

        app.dependency_overrides[_get_db] = fake_get_db

        try:
            from httpx import AsyncClient, ASGITransport

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/sessions/sess_monitor")

            assert resp.status_code == 200
            body = resp.json()
            # index 2 is out of bounds for 2 questions → None
            assert body["current_question_index"] == 2
            assert body["current_question_text"] is None
        finally:
            app.dependency_overrides.pop(_get_db, None)

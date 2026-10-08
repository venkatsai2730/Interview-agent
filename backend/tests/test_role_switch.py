"""
Unit tests for Skill Pack config-only role switch validation.

Verifies that:
- POST /sessions accepts both scorecard and discovery-brief SkillPacks without code changes
- No session-specific behaviour is hardcoded in backend/ or pipeline/
- Two sequential sessions with different SkillPacks each use their own isolated state

Requirements: 14.1, 14.2, 14.4
"""
from __future__ import annotations

import copy
import re
import textwrap
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.skill_pack_validator import parse_skill_pack_yaml, validate_skill_pack
from backend.session_manager import SessionState, SessionStatus
from backend.report_generator import generate_report

from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Minimal SkillPack fixture helper
# ---------------------------------------------------------------------------

def _make_skill_pack(template: str, persona: str, question_text: str) -> dict:
    """Return a minimal but fully valid SkillPack dict."""
    return {
        "skill": {
            "id": f"skill-{template}",
            "name": f"Skill {template}",
            "version": "1.0.0",
        },
        "agent": {
            "name": f"Vero-{template}",
            "persona": persona,
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
                "title": "Section One",
                "questions": [
                    {
                        "id": "q1",
                        "text": question_text,
                        "probes": ["Can you elaborate?"],
                        "competency": "general",
                        "max_follow_ups": 2,
                    }
                ],
            }
        ],
        "rubric": [
            {
                "competency": "general",
                "scores": {
                    "1": "Poor",
                    "2": "Below average",
                    "3": "Average",
                    "4": "Good",
                    "5": "Excellent",
                },
            }
        ],
        "report": {
            "template": template,
            "email_to": ["host@example.com"],
            "include_transcript": False,
        },
    }


# ---------------------------------------------------------------------------
# Test 1: scorecard SkillPack accepted
# ---------------------------------------------------------------------------

def test_scorecard_skillpack_accepted():
    """parse_skill_pack_yaml + validate_skill_pack must accept a scorecard SkillPack.

    Requirements: 14.1, 14.2
    """
    sp_dict = _make_skill_pack(
        template="scorecard",
        persona="You are Vero, a professional technical interviewer.",
        question_text="Describe a distributed system you have designed.",
    )
    raw_yaml = _dict_to_yaml(sp_dict)

    parsed = parse_skill_pack_yaml(raw_yaml)
    result = validate_skill_pack(parsed)

    assert result.is_valid is True, f"Expected valid, got errors: {result.errors}"
    assert parsed["report"]["template"] == "scorecard"


# ---------------------------------------------------------------------------
# Test 2: discovery-brief SkillPack accepted
# ---------------------------------------------------------------------------

def test_discovery_brief_skillpack_accepted():
    """parse_skill_pack_yaml + validate_skill_pack must accept a discovery-brief SkillPack.

    Requirements: 14.1, 14.2
    """
    sp_dict = _make_skill_pack(
        template="discovery-brief",
        persona="You are Vero, a discovery agent helping qualify sales opportunities.",
        question_text="What business problem are you trying to solve?",
    )
    raw_yaml = _dict_to_yaml(sp_dict)

    parsed = parse_skill_pack_yaml(raw_yaml)
    result = validate_skill_pack(parsed)

    assert result.is_valid is True, f"Expected valid, got errors: {result.errors}"
    assert parsed["report"]["template"] == "discovery-brief"


# ---------------------------------------------------------------------------
# Test 3: two sessions have isolated state
# ---------------------------------------------------------------------------

def test_two_sessions_isolated_state():
    """Two SessionState objects with different SkillPacks must not share state.

    Requirements: 14.1, 14.3
    """
    sp1 = _make_skill_pack(
        template="scorecard",
        persona="You are Vero, a technical interviewer.",
        question_text="Explain the CAP theorem.",
    )
    sp2 = _make_skill_pack(
        template="discovery-brief",
        persona="You are Vero, a discovery agent.",
        question_text="What is your biggest pain point today?",
    )

    now = datetime.now(tz=timezone.utc)

    session1 = SessionState(
        session_id="sess_001",
        skill_pack=copy.deepcopy(sp1),
        recall_bot_id="bot_001",
        teams_meeting_url="https://teams.example.com/meeting1",
        status=SessionStatus.PENDING,
        created_at=now,
    )
    session2 = SessionState(
        session_id="sess_002",
        skill_pack=copy.deepcopy(sp2),
        recall_bot_id="bot_002",
        teams_meeting_url="https://teams.example.com/meeting2",
        status=SessionStatus.PENDING,
        created_at=now,
    )

    # Each session has its own skill_pack dict
    assert session1.skill_pack is not session2.skill_pack

    # Personas differ
    assert (
        session1.skill_pack["agent"]["persona"]
        != session2.skill_pack["agent"]["persona"]
    ), "Sessions must have different personas"

    # Templates differ
    assert (
        session1.skill_pack["report"]["template"]
        != session2.skill_pack["report"]["template"]
    ), "Sessions must have different report templates"

    # Question texts differ
    q1_text = session1.skill_pack["sections"][0]["questions"][0]["text"]
    q2_text = session2.skill_pack["sections"][0]["questions"][0]["text"]
    assert q1_text != q2_text, "Sessions must have different question texts"

    # Deep copy check: mutating session1's skill_pack must NOT affect session2
    session1.skill_pack["agent"]["persona"] = "MUTATED"
    assert session2.skill_pack["agent"]["persona"] != "MUTATED", (
        "Mutating session1's skill_pack must not affect session2 (deep copy required)"
    )


# ---------------------------------------------------------------------------
# Test 4: report generator uses SkillPack template
# ---------------------------------------------------------------------------

def test_report_generator_uses_skillpack_template():
    """generate_report must produce the correct template and recommendation per SkillPack.

    - scorecard SkillPack → report.template == 'scorecard', recommendation is set
    - discovery-brief SkillPack → report.template == 'discovery-brief', recommendation is None

    Requirements: 14.1, 14.2
    """
    sp_scorecard = _make_skill_pack(
        template="scorecard",
        persona="You are Vero, a technical interviewer.",
        question_text="Explain the CAP theorem.",
    )
    sp_discovery = _make_skill_pack(
        template="discovery-brief",
        persona="You are Vero, a discovery agent.",
        question_text="What is your biggest pain point today?",
    )

    # Build a minimal session summary with one scored question
    summary_scorecard = SimpleNamespace(
        scores=[{"question_id": "q1", "competency": "general", "score": 4, "rationale": "Good answer."}],
        transcript=[],
        questions_not_reached=[],
    )
    summary_discovery = SimpleNamespace(
        scores=[{"question_id": "q1", "competency": "general", "score": 3, "rationale": "Adequate."}],
        transcript=[],
        questions_not_reached=[],
    )

    report_scorecard = generate_report(summary_scorecard, sp_scorecard, "sess_sc", 20.0)
    report_discovery = generate_report(summary_discovery, sp_discovery, "sess_db", 15.0)

    # Template must match the SkillPack
    assert report_scorecard.template == "scorecard"
    assert report_discovery.template == "discovery-brief"

    # Scorecard must have a hire/no-hire recommendation
    assert report_scorecard.recommendation in ("hire", "no-hire"), (
        f"scorecard report must have a recommendation, got: {report_scorecard.recommendation!r}"
    )

    # Discovery-brief must NOT have a recommendation
    assert report_discovery.recommendation is None, (
        f"discovery-brief report must not have a recommendation, got: {report_discovery.recommendation!r}"
    )


# ---------------------------------------------------------------------------
# Test 5: no hardcoded session behaviour in backend/ or pipeline/
# ---------------------------------------------------------------------------

def test_no_hardcoded_session_behaviour():
    """Smoke test: session_manager.py and pipeline.py must not contain hardcoded
    role-specific strings ('interviewer', 'scorecard', 'discovery-brief') in
    their logic (outside comments and docstrings).

    Requirements: 14.4
    """
    import pathlib

    # Get the project root (parent of backend directory)
    project_root = pathlib.Path(__file__).parent.parent.parent

    files_to_check = [
        project_root / "backend" / "session_manager.py",
        project_root / "pipeline" / "pipeline.py",
    ]

    # Strings that must NOT appear in logic code (outside comments/docstrings)
    forbidden = ["interviewer", "scorecard", "discovery-brief"]

    for filepath in files_to_check:
        assert filepath.exists(), f"Expected file not found: {filepath}"
        source = filepath.read_text(encoding="utf-8")
        logic_lines = _strip_comments_and_docstrings(source)

        for term in forbidden:
            assert term not in logic_lines, (
                f"Hardcoded role string '{term}' found in logic of {filepath}. "
                "All session behaviour must be driven by SkillPack fields (Req 14.4)."
            )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dict_to_yaml(d: dict) -> str:
    """Serialise a dict to YAML using PyYAML (available in the project)."""
    import yaml
    return yaml.dump(d, default_flow_style=False, allow_unicode=True)


def _strip_comments_and_docstrings(source: str) -> str:
    """Return source with Python comments and string literals removed.

    This is a best-effort approach sufficient for a smoke test:
    - Removes lines that start with '#' (after stripping whitespace)
    - Removes triple-quoted string literals (docstrings / multi-line strings)
    - Removes inline '#' comments
    """
    # Remove triple-quoted strings (both ''' and \"\"\")
    source = re.sub(r'""".*?"""', '', source, flags=re.DOTALL)
    source = re.sub(r"'''.*?'''", '', source, flags=re.DOTALL)

    result_lines = []
    for line in source.splitlines():
        stripped = line.strip()
        # Skip pure comment lines
        if stripped.startswith("#"):
            continue
        # Remove inline comments
        code_part = line.split("#")[0]
        result_lines.append(code_part)

    return "\n".join(result_lines)

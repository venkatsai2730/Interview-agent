"""Unit tests for skill_pack_validator."""
import pytest
import yaml

from backend.skill_pack_validator import (
    ParseError,
    ValidationResult,
    parse_skill_pack_yaml,
    validate_skill_pack,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_SKILL_PACK = {
    "skill": {"id": "interviewer-v1", "name": "Senior Backend Engineer", "version": "1.0.0"},
    "agent": {
        "name": "Vero",
        "persona": "You are Vero, a professional technical interviewer.",
        "language": "en-US",
        "max_duration_minutes": 45,
        "model_preferences": [
            {"provider": "bedrock", "model": "anthropic.claude-3-5-sonnet-20241022-v2:0"}
        ],
        "tts_voice": "cartesia:sonic-english",
    },
    "sections": [
        {
            "id": "system-design",
            "title": "System Design",
            "questions": [
                {
                    "id": "q1",
                    "text": "Describe a distributed system you designed.",
                    "probes": ["What were the scaling challenges?"],
                    "competency": "system-design",
                    "max_follow_ups": 2,
                }
            ],
        }
    ],
    "rubric": [
        {
            "competency": "system-design",
            "scores": {
                1: "No understanding",
                2: "Basic understanding",
                3: "Adequate",
                4: "Strong",
                5: "Expert",
            },
        }
    ],
    "report": {
        "template": "scorecard",
        "email_to": ["hiring@example.com"],
        "include_transcript": True,
    },
}

VALID_YAML = yaml.dump(VALID_SKILL_PACK)


# ---------------------------------------------------------------------------
# parse_skill_pack_yaml
# ---------------------------------------------------------------------------

class TestParseSkillPackYaml:
    def test_valid_yaml_returns_dict(self):
        result = parse_skill_pack_yaml(VALID_YAML)
        assert isinstance(result, dict)
        assert result["skill"]["id"] == "interviewer-v1"

    def test_empty_yaml_returns_empty_dict(self):
        result = parse_skill_pack_yaml("")
        assert result == {}

    def test_syntax_error_raises_parse_error(self):
        bad_yaml = "key: [\n  unclosed"
        with pytest.raises(ParseError) as exc_info:
            parse_skill_pack_yaml(bad_yaml)
        err = exc_info.value
        assert isinstance(err.line, int)
        assert isinstance(err.message, str)

    def test_parse_error_has_line_number(self):
        # Inject a syntax error at a known line
        lines = ["valid_key: value\n", "another: value\n", "bad: [\n", "  unclosed\n"]
        bad_yaml = "".join(lines)
        with pytest.raises(ParseError) as exc_info:
            parse_skill_pack_yaml(bad_yaml)
        # Line number should be > 0 (pointing somewhere in the file)
        assert exc_info.value.line > 0

    def test_parse_error_line_1_syntax(self):
        bad_yaml = ": invalid yaml {"
        with pytest.raises(ParseError) as exc_info:
            parse_skill_pack_yaml(bad_yaml)
        assert exc_info.value.line >= 1


# ---------------------------------------------------------------------------
# validate_skill_pack — happy path
# ---------------------------------------------------------------------------

class TestValidateSkillPackValid:
    def test_valid_skill_pack_passes(self):
        result = validate_skill_pack(VALID_SKILL_PACK)
        assert result.is_valid is True
        assert result.errors == []

    def test_all_valid_templates_accepted(self):
        for template in ("scorecard", "discovery-brief", "audit-log", "coaching-report"):
            sp = {**VALID_SKILL_PACK, "report": {**VALID_SKILL_PACK["report"], "template": template}}
            result = validate_skill_pack(sp)
            assert result.is_valid is True, f"Template {template!r} should be valid"

    def test_max_duration_boundary_1(self):
        sp = dict(VALID_SKILL_PACK)
        sp["agent"] = {**sp["agent"], "max_duration_minutes": 1}
        assert validate_skill_pack(sp).is_valid is True

    def test_max_duration_boundary_120(self):
        sp = dict(VALID_SKILL_PACK)
        sp["agent"] = {**sp["agent"], "max_duration_minutes": 120}
        assert validate_skill_pack(sp).is_valid is True


# ---------------------------------------------------------------------------
# validate_skill_pack — missing required fields
# ---------------------------------------------------------------------------

class TestValidateSkillPackMissingFields:
    def test_missing_skill_id(self):
        sp = {**VALID_SKILL_PACK, "skill": {"name": "x", "version": "1.0.0"}}
        result = validate_skill_pack(sp)
        assert result.is_valid is False
        assert "skill.id" in result.errors

    def test_missing_agent_name(self):
        sp = dict(VALID_SKILL_PACK)
        sp["agent"] = {k: v for k, v in sp["agent"].items() if k != "name"}
        result = validate_skill_pack(sp)
        assert result.is_valid is False
        assert "agent.name" in result.errors

    def test_missing_multiple_fields_all_listed(self):
        # Remove skill.id and agent.persona
        sp = {
            **VALID_SKILL_PACK,
            "skill": {"name": "x", "version": "1.0.0"},
            "agent": {k: v for k, v in VALID_SKILL_PACK["agent"].items() if k != "persona"},
        }
        result = validate_skill_pack(sp)
        assert result.is_valid is False
        assert "skill.id" in result.errors
        assert "agent.persona" in result.errors

    def test_empty_dict_lists_all_top_level_errors(self):
        result = validate_skill_pack({})
        assert result.is_valid is False
        # Should have many errors
        assert len(result.errors) > 5


# ---------------------------------------------------------------------------
# validate_skill_pack — enum validation
# ---------------------------------------------------------------------------

class TestValidateSkillPackEnums:
    def test_invalid_template_rejected(self):
        sp = {**VALID_SKILL_PACK, "report": {**VALID_SKILL_PACK["report"], "template": "unknown"}}
        result = validate_skill_pack(sp)
        assert result.is_valid is False
        assert "report.template" in result.errors

    def test_missing_template_rejected(self):
        report = {k: v for k, v in VALID_SKILL_PACK["report"].items() if k != "template"}
        sp = {**VALID_SKILL_PACK, "report": report}
        result = validate_skill_pack(sp)
        assert result.is_valid is False
        assert "report.template" in result.errors


# ---------------------------------------------------------------------------
# validate_skill_pack — max_duration_minutes boundary
# ---------------------------------------------------------------------------

class TestMaxDurationMinutes:
    def test_zero_rejected(self):
        sp = dict(VALID_SKILL_PACK)
        sp["agent"] = {**sp["agent"], "max_duration_minutes": 0}
        result = validate_skill_pack(sp)
        assert result.is_valid is False
        assert "agent.max_duration_minutes" in result.errors

    def test_121_rejected(self):
        sp = dict(VALID_SKILL_PACK)
        sp["agent"] = {**sp["agent"], "max_duration_minutes": 121}
        result = validate_skill_pack(sp)
        assert result.is_valid is False
        assert "agent.max_duration_minutes" in result.errors

    def test_negative_rejected(self):
        sp = dict(VALID_SKILL_PACK)
        sp["agent"] = {**sp["agent"], "max_duration_minutes": -5}
        result = validate_skill_pack(sp)
        assert result.is_valid is False
        assert "agent.max_duration_minutes" in result.errors

    def test_string_value_rejected(self):
        sp = dict(VALID_SKILL_PACK)
        sp["agent"] = {**sp["agent"], "max_duration_minutes": "45"}
        result = validate_skill_pack(sp)
        assert result.is_valid is False
        assert "agent.max_duration_minutes" in result.errors


# ---------------------------------------------------------------------------
# validate_skill_pack — model_preferences
# ---------------------------------------------------------------------------

class TestModelPreferences:
    def test_empty_list_rejected(self):
        sp = dict(VALID_SKILL_PACK)
        sp["agent"] = {**sp["agent"], "model_preferences": []}
        result = validate_skill_pack(sp)
        assert result.is_valid is False
        assert "agent.model_preferences" in result.errors

    def test_missing_provider_rejected(self):
        sp = dict(VALID_SKILL_PACK)
        sp["agent"] = {**sp["agent"], "model_preferences": [{"model": "some-model"}]}
        result = validate_skill_pack(sp)
        assert result.is_valid is False
        assert "agent.model_preferences[0].provider" in result.errors

    def test_missing_model_rejected(self):
        sp = dict(VALID_SKILL_PACK)
        sp["agent"] = {**sp["agent"], "model_preferences": [{"provider": "bedrock"}]}
        result = validate_skill_pack(sp)
        assert result.is_valid is False
        assert "agent.model_preferences[0].model" in result.errors


# ---------------------------------------------------------------------------
# validate_skill_pack — sections and questions
# ---------------------------------------------------------------------------

class TestSectionsAndQuestions:
    def test_empty_sections_rejected(self):
        sp = {**VALID_SKILL_PACK, "sections": []}
        result = validate_skill_pack(sp)
        assert result.is_valid is False
        assert "sections" in result.errors

    def test_question_missing_text_rejected(self):
        q = {k: v for k, v in VALID_SKILL_PACK["sections"][0]["questions"][0].items() if k != "text"}
        sp = {
            **VALID_SKILL_PACK,
            "sections": [{**VALID_SKILL_PACK["sections"][0], "questions": [q]}],
        }
        result = validate_skill_pack(sp)
        assert result.is_valid is False
        assert "sections[0].questions[0].text" in result.errors

    def test_question_missing_probes_rejected(self):
        q = {k: v for k, v in VALID_SKILL_PACK["sections"][0]["questions"][0].items() if k != "probes"}
        sp = {
            **VALID_SKILL_PACK,
            "sections": [{**VALID_SKILL_PACK["sections"][0], "questions": [q]}],
        }
        result = validate_skill_pack(sp)
        assert result.is_valid is False
        assert "sections[0].questions[0].probes" in result.errors

    def test_max_follow_ups_out_of_range_rejected(self):
        q = {**VALID_SKILL_PACK["sections"][0]["questions"][0], "max_follow_ups": 11}
        sp = {
            **VALID_SKILL_PACK,
            "sections": [{**VALID_SKILL_PACK["sections"][0], "questions": [q]}],
        }
        result = validate_skill_pack(sp)
        assert result.is_valid is False
        assert "sections[0].questions[0].max_follow_ups" in result.errors


# ---------------------------------------------------------------------------
# validate_skill_pack — rubric
# ---------------------------------------------------------------------------

class TestRubric:
    def test_empty_rubric_rejected(self):
        sp = {**VALID_SKILL_PACK, "rubric": []}
        result = validate_skill_pack(sp)
        assert result.is_valid is False
        assert "rubric" in result.errors

    def test_rubric_missing_score_key_rejected(self):
        entry = {
            "competency": "system-design",
            "scores": {1: "a", 2: "b", 3: "c", 4: "d"},  # missing 5
        }
        sp = {**VALID_SKILL_PACK, "rubric": [entry]}
        result = validate_skill_pack(sp)
        assert result.is_valid is False
        assert "rubric[0].scores.5" in result.errors

    def test_rubric_missing_competency_rejected(self):
        entry = {"scores": {1: "a", 2: "b", 3: "c", 4: "d", 5: "e"}}
        sp = {**VALID_SKILL_PACK, "rubric": [entry]}
        result = validate_skill_pack(sp)
        assert result.is_valid is False
        assert "rubric[0].competency" in result.errors


# ---------------------------------------------------------------------------
# validate_skill_pack — report
# ---------------------------------------------------------------------------

class TestReport:
    def test_empty_email_to_rejected(self):
        sp = {**VALID_SKILL_PACK, "report": {**VALID_SKILL_PACK["report"], "email_to": []}}
        result = validate_skill_pack(sp)
        assert result.is_valid is False
        assert "report.email_to" in result.errors

    def test_missing_include_transcript_rejected(self):
        report = {k: v for k, v in VALID_SKILL_PACK["report"].items() if k != "include_transcript"}
        sp = {**VALID_SKILL_PACK, "report": report}
        result = validate_skill_pack(sp)
        assert result.is_valid is False
        assert "report.include_transcript" in result.errors

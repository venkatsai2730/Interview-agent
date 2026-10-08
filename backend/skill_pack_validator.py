"""Skill Pack YAML parsing and validation."""
from __future__ import annotations

from dataclasses import dataclass, field

import yaml


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class ParseError(Exception):
    """Raised when the Skill Pack YAML cannot be parsed."""

    def __init__(self, line: int, message: str) -> None:
        self.line = line
        self.message = message
        super().__init__(f"YAML parse error at line {line}: {message}")


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class ValidationResult:
    is_valid: bool
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

VALID_TEMPLATES = {"scorecard", "discovery-brief", "audit-log", "coaching-report"}

VALID_INPUT_TYPES = {"string", "number", "boolean", "enum", "text", "file"}

VALID_CHANNELS = {"teams", "phone"}


def parse_skill_pack_yaml(raw: str) -> dict:
    """Parse a YAML string into a dict.

    Raises:
        ParseError: if the YAML contains a syntax error.
    """
    try:
        result = yaml.safe_load(raw)
    except (yaml.scanner.ScannerError, yaml.parser.ParserError) as exc:
        line = 0
        if exc.problem_mark is not None:
            line = exc.problem_mark.line + 1  # convert 0-indexed to 1-indexed
        raise ParseError(line=line, message=str(exc.problem)) from exc
    except yaml.YAMLError as exc:
        raise ParseError(line=0, message=str(exc)) from exc

    if result is None:
        result = {}
    return result


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def _get(d: dict, *keys: str):
    """Safely traverse nested dicts; return None if any key is missing."""
    current = d
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _check_required_field(sp: dict, path: str, errors: list[str]) -> bool:
    """Return True if the field exists and is not None."""
    keys = path.split(".")
    value = _get(sp, *keys)
    if value is None:
        errors.append(path)
        return False
    return True


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_skill_pack(sp: dict) -> ValidationResult:
    """Validate a parsed Skill Pack dict.

    Returns a ValidationResult listing ALL invalid/missing fields.
    """
    errors: list[str] = []

    # ------------------------------------------------------------------
    # Top-level required scalar fields
    # ------------------------------------------------------------------
    for path in (
        "skill.id",
        "skill.name",
        "skill.version",
        "agent.name",
        "agent.persona",
        "agent.language",
        "agent.tts_voice",
    ):
        _check_required_field(sp, path, errors)

    # ------------------------------------------------------------------
    # agent.max_duration_minutes — must be int in [1, 120]
    # ------------------------------------------------------------------
    max_dur = _get(sp, "agent", "max_duration_minutes")
    if max_dur is None:
        errors.append("agent.max_duration_minutes")
    elif not isinstance(max_dur, int) or not (1 <= max_dur <= 120):
        errors.append("agent.max_duration_minutes")

    # ------------------------------------------------------------------
    # agent.model_preferences — non-empty list, each entry has provider + model
    # ------------------------------------------------------------------
    model_prefs = _get(sp, "agent", "model_preferences")
    if not isinstance(model_prefs, list) or len(model_prefs) == 0:
        errors.append("agent.model_preferences")
    else:
        for i, pref in enumerate(model_prefs):
            if not isinstance(pref, dict):
                errors.append(f"agent.model_preferences[{i}]")
                continue
            if "provider" not in pref:
                errors.append(f"agent.model_preferences[{i}].provider")
            if "model" not in pref:
                errors.append(f"agent.model_preferences[{i}].model")

    # ------------------------------------------------------------------
    # sections — non-empty list, each section has id, title, and either questions or objectives
    # ------------------------------------------------------------------
    sections = _get(sp, "sections")
    if not isinstance(sections, list) or len(sections) == 0:
        errors.append("sections")
    else:
        for si, section in enumerate(sections):
            if not isinstance(section, dict):
                errors.append(f"sections[{si}]")
                continue
            for field_name in ("id", "title"):
                if not section.get(field_name):
                    errors.append(f"sections[{si}].{field_name}")

            # Support both guided (questions) and intelligent (objectives) modes
            mode = section.get("mode", "guided")  # Default to guided for backward compatibility
            questions = section.get("questions")
            objectives = section.get("objectives")

            if mode == "guided":
                # Guided mode requires questions
                if not isinstance(questions, list) or len(questions) == 0:
                    errors.append(f"sections[{si}].questions")
                else:
                    for qi, question in enumerate(questions):
                        if not isinstance(question, dict):
                            errors.append(f"sections[{si}].questions[{qi}]")
                            continue
                        for qfield in ("id", "text", "competency"):
                            if not question.get(qfield):
                                errors.append(f"sections[{si}].questions[{qi}].{qfield}")

                        # probes must be a list
                        probes = question.get("probes")
                        if not isinstance(probes, list):
                            errors.append(f"sections[{si}].questions[{qi}].probes")

                        # max_follow_ups must be int in [0, 10]
                        mfu = question.get("max_follow_ups")
                        if mfu is None:
                            errors.append(f"sections[{si}].questions[{qi}].max_follow_ups")
                        elif not isinstance(mfu, int) or not (0 <= mfu <= 10):
                            errors.append(f"sections[{si}].questions[{qi}].max_follow_ups")
            elif mode == "intelligent":
                # Intelligent mode requires objectives instead of questions
                if not objectives or not isinstance(objectives, str):
                    errors.append(f"sections[{si}].objectives")
            else:
                errors.append(f"sections[{si}].mode (must be 'guided' or 'intelligent')")

    # ------------------------------------------------------------------
    # rubric — non-empty list, each entry has competency + scores (keys 1-5)
    # ------------------------------------------------------------------
    rubric = _get(sp, "rubric")
    if not isinstance(rubric, list) or len(rubric) == 0:
        errors.append("rubric")
    else:
        for ri, entry in enumerate(rubric):
            if not isinstance(entry, dict):
                errors.append(f"rubric[{ri}]")
                continue
            if not entry.get("competency"):
                errors.append(f"rubric[{ri}].competency")
            scores = entry.get("scores")
            if not isinstance(scores, dict):
                errors.append(f"rubric[{ri}].scores")
            else:
                for key in (1, 2, 3, 4, 5):
                    # YAML may parse numeric keys as ints
                    if key not in scores and str(key) not in scores:
                        errors.append(f"rubric[{ri}].scores.{key}")

    # ------------------------------------------------------------------
    # report.template — must be one of the valid enum values
    # ------------------------------------------------------------------
    template = _get(sp, "report", "template")
    if template is None:
        errors.append("report.template")
    elif template not in VALID_TEMPLATES:
        errors.append("report.template")

    # ------------------------------------------------------------------
    # report.email_to — non-empty list
    # ------------------------------------------------------------------
    email_to = _get(sp, "report", "email_to")
    if not isinstance(email_to, list) or len(email_to) == 0:
        errors.append("report.email_to")

    # ------------------------------------------------------------------
    # report.include_transcript — required boolean
    # ------------------------------------------------------------------
    include_transcript = _get(sp, "report", "include_transcript")
    if include_transcript is None:
        errors.append("report.include_transcript")

    # ------------------------------------------------------------------
    # channels — optional, defaults to ["teams", "phone"]
    # ------------------------------------------------------------------
    channels = _get(sp, "channels")
    if channels is not None:
        if not isinstance(channels, list):
            errors.append("channels")
        else:
            for i, ch in enumerate(channels):
                if ch not in VALID_CHANNELS:
                    errors.append(f"channels[{i}]")

    # ------------------------------------------------------------------
    # input_schema — optional, but if present must be valid
    # ------------------------------------------------------------------
    input_schema = _get(sp, "input_schema")
    if input_schema is not None:
        if not isinstance(input_schema, list):
            errors.append("input_schema")
        else:
            for i, field_def in enumerate(input_schema):
                if not isinstance(field_def, dict):
                    errors.append(f"input_schema[{i}]")
                    continue
                # Required fields for each input definition
                if not field_def.get("name"):
                    errors.append(f"input_schema[{i}].name")
                if not field_def.get("type"):
                    errors.append(f"input_schema[{i}].type")
                elif field_def.get("type") not in VALID_INPUT_TYPES:
                    errors.append(f"input_schema[{i}].type")
                # Enum type requires values
                if field_def.get("type") == "enum":
                    values = field_def.get("values")
                    if not isinstance(values, list) or len(values) == 0:
                        errors.append(f"input_schema[{i}].values")

    if errors:
        return ValidationResult(is_valid=False, errors=errors)
    return ValidationResult(is_valid=True, errors=[])

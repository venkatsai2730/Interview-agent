"""RPC Bridge — stdin/stdout JSONL serialisation between Pipecat and pi_agent.

All messages are single-line JSON objects terminated by a newline.
Both sides validate message schema on receipt; invalid messages are logged
and a {"type":"error"} response is sent without terminating the session.
"""
from __future__ import annotations

import dataclasses
import json
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Message dataclasses — Pipecat → pi_agent
# ---------------------------------------------------------------------------

@dataclass
class TurnMessage:
    session_id: str
    speaker: str
    transcript: str
    turn_index: int
    timestamp_ms: int
    type: str = "turn"


@dataclass
class SessionStartMessage:
    session_id: str
    skill_pack: dict
    type: str = "session_start"


@dataclass
class SessionEndMessage:
    session_id: str
    reason: str  # all_questions_complete | max_duration_reached | manual
    type: str = "session_end"


@dataclass
class SilenceTimeoutMessage:
    session_id: str
    silence_duration_ms: int
    consecutive_count: int
    type: str = "silence_timeout"


# ---------------------------------------------------------------------------
# Message dataclasses — pi_agent → Pipecat
# ---------------------------------------------------------------------------

@dataclass
class TurnOutputMessage:
    session_id: str
    turn_index: int
    next_utterance: str
    action: str  # follow_up | clarify | advance | close
    question_id: str
    competency: str
    flags: list = field(default_factory=list)
    score: Optional[int] = None
    score_rationale: Optional[str] = None
    type: str = "turn_output"


@dataclass
class SessionSummaryMessage:
    session_id: str
    scores: list  # [{question_id, competency, score, rationale}]
    transcript: list  # [{speaker, text, timestamp_ms}]
    questions_not_reached: list
    type: str = "session_summary"


# ---------------------------------------------------------------------------
# Registry: type string → dataclass
# ---------------------------------------------------------------------------

_TYPE_MAP: dict[str, type] = {
    "turn": TurnMessage,
    "session_start": SessionStartMessage,
    "session_end": SessionEndMessage,
    "silence_timeout": SilenceTimeoutMessage,
    "turn_output": TurnOutputMessage,
    "session_summary": SessionSummaryMessage,
}

# Required fields per message type (excluding "type" itself)
_REQUIRED_FIELDS: dict[str, set[str]] = {
    "turn": {"session_id", "speaker", "transcript", "turn_index", "timestamp_ms"},
    "session_start": {"session_id", "skill_pack"},
    "session_end": {"session_id", "reason"},
    "silence_timeout": {"session_id", "silence_duration_ms", "consecutive_count"},
    "turn_output": {"session_id", "turn_index", "next_utterance", "action", "question_id", "competency"},
    "session_summary": {"session_id", "scores", "transcript", "questions_not_reached"},
}


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------

def serialize_rpc_message(msg: object) -> str:
    """Serialise a dataclass message to a JSONL string (JSON + newline).

    Args:
        msg: Any of the RPC message dataclasses.

    Returns:
        A single-line JSON string terminated by '\\n'.
    """
    return json.dumps(dataclasses.asdict(msg)) + "\n"


# ---------------------------------------------------------------------------
# Deserialisation
# ---------------------------------------------------------------------------

def parse_rpc_message(line: str) -> object:
    """Parse a JSONL line into the appropriate message dataclass.

    Validates that the required fields are present for the given message type.
    On any error, logs the problem and returns an error dict (not a dataclass)
    so the caller can forward {"type":"error"} to the other side.

    Args:
        line: A single JSONL line (with or without trailing newline).

    Returns:
        A message dataclass instance, or a dict {"type": "error", "message": str}
        if parsing or validation fails.
    """
    line = line.strip()
    if not line:
        logger.warning("rpc_bridge: received empty line")
        return {"type": "error", "message": "empty line"}

    try:
        data = json.loads(line)
    except json.JSONDecodeError as exc:
        logger.error("rpc_bridge: JSON decode error: %s | raw=%r", exc, line)
        return {"type": "error", "message": f"JSON decode error: {exc}"}

    if not isinstance(data, dict):
        logger.error("rpc_bridge: expected JSON object, got %s", type(data).__name__)
        return {"type": "error", "message": "expected JSON object"}

    msg_type = data.get("type")
    if msg_type not in _TYPE_MAP:
        logger.error("rpc_bridge: unknown message type %r", msg_type)
        return {"type": "error", "message": f"unknown type: {msg_type!r}"}

    required = _REQUIRED_FIELDS.get(msg_type, set())
    missing = required - data.keys()
    if missing:
        logger.error(
            "rpc_bridge: message type %r missing fields %s", msg_type, sorted(missing)
        )
        return {
            "type": "error",
            "message": f"missing fields for {msg_type}: {sorted(missing)}",
        }

    cls = _TYPE_MAP[msg_type]
    # Build kwargs from data, ignoring unknown keys to stay forward-compatible
    known_fields = {f.name for f in dataclasses.fields(cls)}
    kwargs = {k: v for k, v in data.items() if k in known_fields}
    try:
        return cls(**kwargs)
    except TypeError as exc:
        logger.error("rpc_bridge: failed to construct %s: %s", cls.__name__, exc)
        return {"type": "error", "message": f"construction error: {exc}"}

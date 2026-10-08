"""Shared Pydantic schemas for request/response models."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Skill Pack schemas
# ---------------------------------------------------------------------------


class ValidateSkillPackRequest(BaseModel):
    yaml_content: str


class SkillPackCreateRequest(BaseModel):
    yaml_content: str
    change_summary: Optional[str] = None


class SkillPackUpdateRequest(BaseModel):
    yaml_content: str
    change_summary: Optional[str] = None


class SectionSummary(BaseModel):
    mode: str
    questions: list[str]  # question texts for guided sections
    objectives: Optional[str]  # objectives text for intelligent sections


class SkillPackSummary(BaseModel):
    id: str
    name: str
    skill_id: str
    version: str
    is_active: bool
    channels: list[str]
    created_at: datetime
    yaml_content: str
    sections_summary: list[SectionSummary] = []


class SkillPackVersionRecord(BaseModel):
    version_number: int
    yaml_content: str
    created_at: datetime
    change_summary: Optional[str]


class GenerateSkillPackRequest(BaseModel):
    description: str  # What this skill needs to do - AI generates everything from this


class GenerateSkillPackResponse(BaseModel):
    yaml_content: str  # Complete skill pack YAML


# ---------------------------------------------------------------------------
# Session schemas
# ---------------------------------------------------------------------------


class CreateSessionRequest(BaseModel):
    yaml_content: Optional[str] = None
    skill_pack_id: Optional[str] = None
    meeting_url: str
    tts_voice: Optional[str] = None
    llm_model: Optional[str] = None
    agent_name: Optional[str] = None
    context_data: Optional[dict] = None
    language: Optional[str] = None  # Sarvam language code (e.g., en-IN, hi-IN)


class CreatePhoneSessionRequest(BaseModel):
    yaml_content: Optional[str] = None
    skill_pack_id: Optional[str] = None
    phone_number: str
    tts_voice: Optional[str] = None
    llm_model: Optional[str] = None
    agent_name: Optional[str] = None
    context_data: Optional[dict] = None


class CreateLiveKitPhoneRequest(BaseModel):
    yaml_content: Optional[str] = None
    skill_pack_id: Optional[str] = None
    phone_number: str
    tts_voice: Optional[str] = None
    llm_model: Optional[str] = None
    agent_name: Optional[str] = None
    context_data: Optional[dict] = None
    language: Optional[str] = None  # Sarvam language code (e.g., en-IN, hi-IN)


class SessionSummary(BaseModel):
    session_id: str
    skill_pack_name: str
    status: str
    created_at: datetime
    ended_at: Optional[datetime]
    duration_minutes: Optional[float]
    turn_count: int


class SessionListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    sessions: list[SessionSummary]


# ---------------------------------------------------------------------------
# Report schemas
# ---------------------------------------------------------------------------


class ReportSummary(BaseModel):
    report_id: str
    session_id: str
    template: str
    generated_at: datetime
    email_sent: bool
    chat_posted: bool

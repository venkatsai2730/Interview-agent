"""ORM models: Session, Turn, Report, SkillPack, SkillPackVersion — SQLAlchemy 2.x declarative style."""
from datetime import datetime
from typing import Optional

from sqlalchemy import ARRAY, BigInteger, Boolean, Integer, Text
from sqlalchemy import JSON
from sqlalchemy import ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP


class Base(DeclarativeBase):
    pass


class Session(Base):
    __tablename__ = "sessions"

    session_id: Mapped[str] = mapped_column(Text, primary_key=True)
    skill_pack: Mapped[dict] = mapped_column(JSON, nullable=False)
    recall_bot_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    meeting_url: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default="now()"
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    ended_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    tts_fallback: Mapped[Optional[bool]] = mapped_column(Boolean, default=False)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Channel: 'teams' (default) or 'phone'
    channel: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default="teams")
    phone_number: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    twilio_call_sid: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Recording URL for phone calls (Twilio recording)
    recording_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Recording URL for Teams calls (Recall.ai recording)
    recall_recording_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Transcript storage for the session
    full_transcript: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # DB-level pipeline guard: set when pipeline is started, cleared on close
    pipeline_started_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    # Context data for skills with input_schema
    context_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)


class Turn(Base):
    __tablename__ = "turns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[Optional[str]] = mapped_column(
        Text, ForeignKey("sessions.session_id"), nullable=True
    )
    turn_index: Mapped[int] = mapped_column(Integer, nullable=False)
    speaker: Mapped[str] = mapped_column(Text, nullable=False)
    transcript: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    question_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    score_rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    competency: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    flags: Mapped[Optional[list]] = mapped_column(ARRAY(Text), nullable=True)
    eou_ts_ms: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    first_audio_ts_ms: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default="now()"
    )


class Report(Base):
    __tablename__ = "reports"

    session_id: Mapped[str] = mapped_column(
        Text, ForeignKey("sessions.session_id"), primary_key=True
    )
    template: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[dict] = mapped_column(JSON, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default="now()"
    )
    email_sent: Mapped[Optional[bool]] = mapped_column(Boolean, default=False)
    chat_posted: Mapped[Optional[bool]] = mapped_column(Boolean, default=False)


class SkillPack(Base):
    __tablename__ = "skill_packs"

    id: Mapped[str] = mapped_column(
        Text, primary_key=True, server_default="gen_random_uuid()::text"
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    skill_id: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[str] = mapped_column(Text, nullable=False)
    yaml_content: Mapped[str] = mapped_column(Text, nullable=False)
    parsed_content: Mapped[dict] = mapped_column(JSONB, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # Channels this skill supports: ['teams'], ['phone'], or ['teams', 'phone']
    channels: Mapped[Optional[list]] = mapped_column(ARRAY(Text), nullable=True, default=list)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default="now()"
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default="now()"
    )


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    session_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default="now()"
    )
    detail: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)


class SkillPackVersion(Base):
    __tablename__ = "skill_pack_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    skill_pack_id: Mapped[Optional[str]] = mapped_column(
        Text, ForeignKey("skill_packs.id", ondelete="CASCADE"), nullable=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    yaml_content: Mapped[str] = mapped_column(Text, nullable=False)
    parsed_content: Mapped[dict] = mapped_column(JSONB, nullable=False)
    change_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default="now()"
    )

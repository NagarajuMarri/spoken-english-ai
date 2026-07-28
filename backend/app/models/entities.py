from datetime import date, datetime, timezone
from uuid import uuid4

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base


def new_id() -> str:
    return str(uuid4())


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Learner(Base):
    __tablename__ = "learners"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(100))
    native_language: Mapped[str] = mapped_column(String(20), default="Telugu")
    proficiency_level: Mapped[str] = mapped_column(String(30), default="STARTER")
    learning_goal: Mapped[str] = mapped_column(String(30), default="GENERAL_FLUENCY")
    daily_goal_minutes: Mapped[int] = mapped_column(Integer, default=10)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    learner_id: Mapped[str] = mapped_column(ForeignKey("learners.id", ondelete="CASCADE"), index=True)
    scenario_id: Mapped[str] = mapped_column(String(50), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    messages: Mapped[list["ConversationMessage"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="ConversationMessage.turn_number"
    )


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"
    __table_args__ = (UniqueConstraint("conversation_id", "turn_number"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    turn_number: Mapped[int] = mapped_column(Integer)
    learner_text: Mapped[str] = mapped_column(Text)
    tutor_response: Mapped[str] = mapped_column(Text)
    correction_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class ProgressRecord(Base):
    __tablename__ = "progress_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    learner_id: Mapped[str] = mapped_column(ForeignKey("learners.id", ondelete="CASCADE"), index=True)
    conversation_id: Mapped[str | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True
    )
    completed_turns: Mapped[int] = mapped_column(Integer, default=0)
    lesson_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    practice_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    scenario_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    proficiency_level: Mapped[str | None] = mapped_column(String(30), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class LessonSession(Base):
    __tablename__ = "lesson_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    learner_id: Mapped[str] = mapped_column(ForeignKey("learners.id", ondelete="CASCADE"), index=True)
    lesson_id: Mapped[str] = mapped_column(String(80), index=True)
    conversation_id: Mapped[str | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), default="STARTED")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0)
    evaluation: Mapped["ConversationEvaluation | None"] = relationship(
        back_populates="lesson_session", uselist=False, cascade="all, delete-orphan"
    )


class ConversationEvaluation(Base):
    __tablename__ = "conversation_evaluations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    lesson_session_id: Mapped[str] = mapped_column(
        ForeignKey("lesson_sessions.id", ondelete="CASCADE"), unique=True
    )
    grammar_score: Mapped[int] = mapped_column(Integer)
    vocabulary_score: Mapped[int] = mapped_column(Integer)
    fluency_score: Mapped[int] = mapped_column(Integer)
    task_completion_score: Mapped[int] = mapped_column(Integer)
    confidence_score: Mapped[int] = mapped_column(Integer)
    overall_score: Mapped[int] = mapped_column(Integer)
    strengths: Mapped[list[str]] = mapped_column(JSON)
    priority_improvements: Mapped[list[str]] = mapped_column(JSON)
    corrected_examples: Mapped[list[str]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    lesson_session: Mapped[LessonSession] = relationship(back_populates="evaluation")


class ConsentRecord(Base):
    __tablename__ = "consent_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    learner_id: Mapped[str] = mapped_column(ForeignKey("learners.id", ondelete="CASCADE"), index=True)
    voice_processing_consent: Mapped[bool] = mapped_column(default=False)
    audio_storage_consent: Mapped[bool] = mapped_column(default=False)
    consent_version: Mapped[str] = mapped_column(String(30))
    consented_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consent_withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class VoiceSession(Base):
    __tablename__ = "voice_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    learner_id: Mapped[str] = mapped_column(ForeignKey("learners.id", ondelete="CASCADE"), index=True)
    scenario_id: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20), default="STARTED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    turns: Mapped[list["VoiceTurn"]] = relationship(
        back_populates="voice_session", cascade="all, delete-orphan", order_by="VoiceTurn.turn_number"
    )
    assets: Mapped[list["AudioAsset"]] = relationship(back_populates="voice_session")


class VoiceTurn(Base):
    __tablename__ = "voice_turns"
    __table_args__ = (UniqueConstraint("voice_session_id", "turn_number"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    voice_session_id: Mapped[str] = mapped_column(ForeignKey("voice_sessions.id", ondelete="CASCADE"), index=True)
    turn_number: Mapped[int] = mapped_column(Integer)
    audio_asset_id: Mapped[str] = mapped_column(ForeignKey("audio_assets.id"))
    transcript: Mapped[str] = mapped_column(Text)
    tutor_text: Mapped[str] = mapped_column(Text)
    correction_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    synthetic_audio_reference: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    voice_session: Mapped[VoiceSession] = relationship(back_populates="turns")


class AudioAsset(Base):
    __tablename__ = "audio_assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    learner_id: Mapped[str] = mapped_column(ForeignKey("learners.id", ondelete="CASCADE"), index=True)
    voice_session_id: Mapped[str] = mapped_column(ForeignKey("voice_sessions.id", ondelete="CASCADE"), index=True)
    media_type: Mapped[str] = mapped_column(String(50))
    storage_key: Mapped[str] = mapped_column(String(200), unique=True)
    status: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    voice_session: Mapped[VoiceSession] = relationship(back_populates="assets")

from datetime import date, datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, event
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base


def new_id() -> str:
    return str(uuid4())


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Learner(Base):
    __tablename__ = "learners"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_account_id: Mapped[str] = mapped_column(
        ForeignKey("user_accounts.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(100))
    native_language: Mapped[str] = mapped_column(String(20), default="Telugu")
    proficiency_level: Mapped[str] = mapped_column(String(30), default="STARTER")
    learning_goal: Mapped[str] = mapped_column(String(30), default="GENERAL_FLUENCY")
    daily_goal_minutes: Mapped[int] = mapped_column(Integer, default=10)
    preferred_tutor_id: Mapped[str] = mapped_column(String(50), default="ananya")
    telugu_explanations_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class UserAccount(Base):
    __tablename__ = "user_accounts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", index=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("user_accounts.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    family_id: Mapped[str] = mapped_column(String(36), index=True)
    parent_token_id: Mapped[str | None] = mapped_column(
        ForeignKey("refresh_tokens.id", ondelete="SET NULL"), unique=True, nullable=True
    )
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    replaced_by_token_id: Mapped[str | None] = mapped_column(
        ForeignKey("refresh_tokens.id", ondelete="SET NULL"), nullable=True
    )
    user_agent: Mapped[str | None] = mapped_column(String(200), nullable=True)
    ip_metadata: Mapped[str | None] = mapped_column(String(80), nullable=True)


class SecurityAuditEvent(Base):
    __tablename__ = "security_audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    event_type: Mapped[str] = mapped_column(String(50), index=True)
    user_id: Mapped[str | None] = mapped_column(
        ForeignKey("user_accounts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    learner_id: Mapped[str | None] = mapped_column(
        ForeignKey("learners.id", ondelete="SET NULL"), nullable=True
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    outcome: Mapped[str] = mapped_column(String(20))
    reason_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    privacy_minimised_network_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent_summary: Mapped[str | None] = mapped_column(String(100), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)


@event.listens_for(SecurityAuditEvent, "before_update")
@event.listens_for(SecurityAuditEvent, "before_delete")
def _security_audit_events_are_append_only(*_) -> None:
    raise ValueError("Security audit events are append-only.")


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
    cleanup_retry_count: Mapped[int] = mapped_column(Integer, default=0)
    cleanup_failure_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    deletion_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    voice_session: Mapped[VoiceSession] = relationship(back_populates="assets")


class LearnerMemoryProfile(Base):
    __tablename__ = "learner_memory_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    learner_id: Mapped[str] = mapped_column(
        ForeignKey("learners.id", ondelete="CASCADE"), unique=True, index=True
    )
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    current_level: Mapped[str] = mapped_column(String(30), default="STARTER")
    preferred_topics: Mapped[list] = mapped_column(JSON, default=list)
    avoided_topics: Mapped[list] = mapped_column(JSON, default=list)
    recent_goals: Mapped[list] = mapped_column(JSON, default=list)
    completed_goals: Mapped[list] = mapped_column(JSON, default=list)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class LearnerMemorySignal(Base):
    __tablename__ = "learner_memory_signals"
    __table_args__ = (UniqueConstraint("learner_id", "category", "normalised_value"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    learner_id: Mapped[str] = mapped_column(ForeignKey("learners.id", ondelete="CASCADE"), index=True)
    category: Mapped[str] = mapped_column(String(30), index=True)
    normalised_value: Mapped[str] = mapped_column(String(200))
    display_value: Mapped[str] = mapped_column(String(200))
    occurrence_count: Mapped[int] = mapped_column(Integer, default=1)
    trend_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AIUsageRecord(Base):
    __tablename__ = "ai_usage_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    learner_id: Mapped[str] = mapped_column(ForeignKey("learners.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("user_accounts.id", ondelete="CASCADE"), index=True)
    voice_session_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    provider_kind: Mapped[str] = mapped_column(String(20), index=True)
    request_count: Mapped[int] = mapped_column(Integer, default=1)
    input_units: Mapped[float] = mapped_column(Float, default=0)
    output_units: Mapped[float] = mapped_column(Float, default=0)
    retries: Mapped[int] = mapped_column(Integer, default=0)
    degraded: Mapped[bool] = mapped_column(Boolean, default=False)
    failed: Mapped[bool] = mapped_column(Boolean, default=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class VoiceProcessingAttempt(Base):
    __tablename__ = "voice_processing_attempts"
    __table_args__ = (UniqueConstraint("voice_turn_id", "idempotency_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    voice_turn_id: Mapped[str] = mapped_column(ForeignKey("voice_turns.id", ondelete="CASCADE"), index=True)
    learner_id: Mapped[str] = mapped_column(ForeignKey("learners.id", ondelete="CASCADE"), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(30), index=True)
    result_json: Mapped[dict] = mapped_column(JSON, default=dict)
    degraded_features: Mapped[list] = mapped_column(JSON, default=list)
    failure_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LessonCacheEntry(Base):
    __tablename__ = "lesson_cache_entries"
    __table_args__ = (UniqueConstraint("cache_key", "content_kind", "version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    cache_key: Mapped[str] = mapped_column(String(160), index=True)
    content_kind: Mapped[str] = mapped_column(String(40), index=True)
    version: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class TTSAudioCacheEntry(Base):
    __tablename__ = "tts_audio_cache_entries"

    cache_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    tutor_voice: Mapped[str] = mapped_column(String(100), index=True)
    privacy_scope: Mapped[str] = mapped_column(String(100), index=True)
    audio_reference: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="COMPLETED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class ConversationSummaryRecord(Base):
    __tablename__ = "conversation_summary_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), unique=True)
    learner_id: Mapped[str] = mapped_column(ForeignKey("learners.id", ondelete="CASCADE"), index=True)
    summary_version: Mapped[int] = mapped_column(Integer, default=1)
    pedagogical_signals: Mapped[dict] = mapped_column(JSON, default=dict)
    summarized_through_turn: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class AICostMetricEvent(Base):
    __tablename__ = "ai_cost_metric_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    learner_id: Mapped[str] = mapped_column(ForeignKey("learners.id", ondelete="CASCADE"), index=True)
    lesson_id: Mapped[str] = mapped_column(String(80), index=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cached_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0)
    response_latency_ms: Mapped[float] = mapped_column(Float, default=0)
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False)
    model_used: Mapped[str] = mapped_column(String(100))
    cost_classification: Mapped[str] = mapped_column(String(40), default="ESTIMATE_NOT_PROVIDER_BILLING")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class CommercialSubscription(Base):
    __tablename__ = "commercial_subscriptions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    learner_id: Mapped[str] = mapped_column(ForeignKey("learners.id", ondelete="CASCADE"), index=True)
    plan_id: Mapped[str] = mapped_column(String(40), index=True)
    status: Mapped[str] = mapped_column(String(30), index=True)
    provider_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    provider_reference: Mapped[str | None] = mapped_column(String(160), unique=True, nullable=True)
    trial_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class CommercialPaymentEvent(Base):
    __tablename__ = "commercial_payment_events"

    event_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    subscription_id: Mapped[str] = mapped_column(ForeignKey("commercial_subscriptions.id", ondelete="CASCADE"), index=True)
    learner_id: Mapped[str] = mapped_column(ForeignKey("learners.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(50), index=True)
    provider_id: Mapped[str] = mapped_column(String(40))
    provider_reference: Mapped[str] = mapped_column(String(160))
    payload_digest: Mapped[str] = mapped_column(String(64))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class CommercialRefundRecord(Base):
    __tablename__ = "commercial_refund_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    subscription_id: Mapped[str] = mapped_column(ForeignKey("commercial_subscriptions.id", ondelete="CASCADE"), index=True)
    learner_id: Mapped[str] = mapped_column(ForeignKey("learners.id", ondelete="CASCADE"), index=True)
    reason: Mapped[str] = mapped_column(String(300))
    requested_by: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(30), default="REQUESTED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class CommercialAuditEvent(Base):
    __tablename__ = "commercial_audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    subscription_id: Mapped[str | None] = mapped_column(ForeignKey("commercial_subscriptions.id", ondelete="SET NULL"), nullable=True, index=True)
    learner_id: Mapped[str | None] = mapped_column(ForeignKey("learners.id", ondelete="SET NULL"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(60), index=True)
    outcome: Mapped[str] = mapped_column(String(20), default="RECORDED")
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


@event.listens_for(CommercialAuditEvent, "before_update")
@event.listens_for(CommercialAuditEvent, "before_delete")
def _commercial_audit_events_are_append_only(*_) -> None:
    raise ValueError("Commercial audit events are append-only.")

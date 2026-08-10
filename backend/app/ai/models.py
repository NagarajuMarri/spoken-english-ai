from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.unicode_safety import normalize_output_text


def _normalize_output_list(value):
    if not isinstance(value, list):
        return value
    return [
        normalize_output_text(item) if isinstance(item, str) else item
        for item in value
    ]


class UsageInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_units: int = Field(default=0, ge=0)
    cached_input_units: int = Field(default=0, ge=0)
    output_units: int = Field(default=0, ge=0)
    provider_requests: int = Field(default=1, ge=0)


class LearningSignals(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grammar_focus: list[str] = Field(max_length=5)
    vocabulary: list[str] = Field(max_length=8)
    confidence: int = Field(ge=0, le=100)
    fluency: int = Field(ge=0, le=100)

    @field_validator("grammar_focus", "vocabulary", mode="before")
    @classmethod
    def normalize_learner_facing_lists(cls, value):
        return _normalize_output_list(value)


class ConversationHistoryTurn(BaseModel):
    learner_message: str = Field(min_length=1, max_length=2000)
    tutor_message: str = Field(min_length=1, max_length=2000)


class AIConversationRequest(BaseModel):
    learner_id: str = Field(min_length=1, max_length=36)
    conversation_id: str = Field(min_length=1, max_length=36)
    learner_level: str = Field(max_length=30)
    learner_age_range: str | None = Field(default=None, max_length=30)
    preferred_language: str | None = Field(default=None, max_length=30)
    tutor_id: str = Field(default="ananya", min_length=1, max_length=50)
    tutor_prompt_profile: str = Field(default="supportive-daily-speaking-v1", max_length=100)
    tutor_vocabulary_profile: str = Field(default="practical-indian-english-v1", max_length=100)
    scenario: str = Field(min_length=1, max_length=80)
    topic: str = Field(min_length=1, max_length=120)
    conversation_history: list[ConversationHistoryTurn] = Field(default_factory=list, max_length=3)
    current_learner_message: str = Field(min_length=1, max_length=2000)
    daily_goal: str | None = Field(default=None, max_length=200)
    known_strengths: list[str] = Field(default_factory=list, max_length=10)
    known_weaknesses: list[str] = Field(default_factory=list, max_length=10)
    recent_corrections: list[str] = Field(default_factory=list, max_length=10)
    allowed_response_length: int = Field(default=500, ge=80, le=2000)
    safety_policy: str = Field(default="supportive_age_appropriate", max_length=100)
    correlation_id: str = Field(min_length=1, max_length=64)


class AIConversationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tutor_message: str = Field(min_length=1, max_length=2000)
    corrected_learner_sentence: str | None = Field(max_length=2000)
    correction_explanation: str | None = Field(max_length=1000)
    grammar_feedback: list[str] = Field(max_length=5)
    vocabulary_suggestions: list[str] = Field(max_length=8)
    conversation_question: str = Field(min_length=1, max_length=500)
    encouragement: str = Field(min_length=1, max_length=300)
    detected_level: str = Field(max_length=30)
    recommended_next_difficulty: str = Field(max_length=30)
    learning_signals: LearningSignals
    provider_metadata_reference: str = Field(min_length=1, max_length=100)
    usage: UsageInfo

    @field_validator(
        "tutor_message", "corrected_learner_sentence", "correction_explanation",
        "conversation_question", "encouragement", mode="before"
    )
    @classmethod
    def reject_unsafe_text(cls, value):
        if value is None:
            return value
        if not isinstance(value, str):
            return value
        lowered = value.lower()
        if any(marker in lowered for marker in ("<script", "javascript:", "system prompt", "api_key", "authorization: bearer")):
            raise ValueError("Unsafe provider output.")
        return normalize_output_text(value)

    @field_validator("grammar_feedback", "vocabulary_suggestions", mode="before")
    @classmethod
    def normalize_learner_facing_lists(cls, value):
        return _normalize_output_list(value)

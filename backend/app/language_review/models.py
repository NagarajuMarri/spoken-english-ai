from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.ai.models import UsageInfo
from backend.app.domain.enums import LanguageMode


class ReviewReasonCode(StrEnum):
    NOT_REQUIRED = "NOT_REQUIRED"
    NATURALIZED_TELUGU = "NATURALIZED_TELUGU"
    IMPROVED_CODE_SWITCHING = "IMPROVED_CODE_SWITCHING"
    SIMPLIFIED_TEACHER_TONE = "SIMPLIFIED_TEACHER_TONE"


class ExpressionHint(StrEnum):
    NEUTRAL = "NEUTRAL"
    POSITIVE = "POSITIVE"
    ENCOURAGING = "ENCOURAGING"
    CORRECTIVE = "CORRECTIVE"


class LanguageReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_tutor_message: str = Field(min_length=1, max_length=2000)
    source_correction_explanation: str | None = Field(max_length=1000)
    source_conversation_question: str = Field(min_length=1, max_length=500)
    source_encouragement: str = Field(min_length=1, max_length=300)
    corrected_learner_sentence: str | None = Field(max_length=2000)
    grammar_feedback: list[str] = Field(max_length=5)
    vocabulary_suggestions: list[str] = Field(max_length=8)
    learning_objective: str = Field(min_length=1, max_length=120)
    learner_level: str = Field(max_length=30)
    language_mode: LanguageMode
    required_learning_terms: list[str] = Field(max_length=20)
    source_content_digest: str = Field(min_length=64, max_length=64)
    correlation_id: str = Field(min_length=1, max_length=64)


class LanguageReviewResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    final_text: str = Field(min_length=1, max_length=2000)
    final_correction_explanation: str | None = Field(max_length=1000)
    final_conversation_question: str = Field(min_length=1, max_length=500)
    final_encouragement: str = Field(min_length=1, max_length=300)
    language_mode: LanguageMode
    review_changed: bool
    review_reason_code: ReviewReasonCode
    preserved_learning_terms: list[str] = Field(max_length=20)
    expression_hint: ExpressionHint
    source_content_digest: str = Field(min_length=64, max_length=64)
    provider_metadata_reference: str = Field(min_length=1, max_length=100)
    usage: UsageInfo

    @field_validator("review_changed", mode="before")
    @classmethod
    def require_json_boolean(cls, value):
        if type(value) is not bool:
            raise ValueError("review_changed must be a JSON boolean")
        return value

    @field_validator(
        "final_text", "final_correction_explanation", "final_conversation_question",
        "final_encouragement", mode="before",
    )
    @classmethod
    def reject_unsafe_text(cls, value):
        if value is None:
            return value
        lowered = value.lower()
        if any(marker in lowered for marker in (
            "<script", "javascript:", "system prompt", "api_key", "authorization: bearer",
        )):
            raise ValueError("Unsafe reviewer output.")
        if any(ord(char) < 32 and char not in "\n\t" for char in value):
            raise ValueError("Invalid control character.")
        return value.strip()

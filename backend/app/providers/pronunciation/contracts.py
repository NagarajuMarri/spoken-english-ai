from typing import Protocol
from pydantic import BaseModel, Field


class PronunciationRequest(BaseModel):
    learner_transcript: str = Field(min_length=1, max_length=4000)
    expected_text: str | None = Field(default=None, max_length=4000)
    audio_asset_reference: str = Field(max_length=200)
    language: str = Field(default="en", max_length=20)
    level: str = Field(max_length=30)
    correlation_id: str = Field(max_length=64)


class PronunciationResult(BaseModel):
    assessment_type: str
    overall_score: int = Field(ge=0, le=100)
    word_accuracy: int = Field(ge=0, le=100)
    fluency_score: int = Field(ge=0, le=100)
    completeness_score: int = Field(ge=0, le=100)
    pronunciation_score: int = Field(ge=0, le=100)
    confidence_score: int | None = Field(default=None, ge=0, le=100)
    word_level_feedback: list[str] = Field(default_factory=list, max_length=100)
    improvement_tips: list[str] = Field(default_factory=list, max_length=10)
    provider_metadata_reference: str = Field(max_length=100)


class PronunciationAssessmentProvider(Protocol):
    def assess(self, request: PronunciationRequest) -> PronunciationResult: ...

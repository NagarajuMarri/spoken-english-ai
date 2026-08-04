from typing import Protocol
from pydantic import BaseModel, Field


class SpeechToTextRequest(BaseModel):
    audio_asset_reference: str = Field(min_length=1, max_length=200)
    content_type: str
    language_hint: str = Field(default="en", max_length=20)
    learner_id: str
    voice_session_id: str
    voice_turn_id: str
    correlation_id: str = Field(max_length=64)
    maximum_duration_seconds: int = Field(default=120, ge=1, le=600)
    duration_seconds: float = Field(default=1, gt=0, le=600)
    size_bytes: int = Field(default=1, ge=0, le=10_000_000)
    provider_options_reference: str | None = Field(default=None, max_length=100)


class SpeechToTextResult(BaseModel):
    transcript: str = Field(min_length=1, max_length=4000)
    detected_language: str = Field(max_length=20)
    confidence: float | None = Field(default=None, ge=0, le=1)
    word_timing_references: list[str] = Field(default_factory=list, max_length=500)
    provider_job_id: str = Field(max_length=100)
    duration_seconds: float = Field(ge=0)
    usage_units: float = Field(ge=0)
    processing_status: str


class SpeechToTextProvider(Protocol):
    def transcribe(self, request: SpeechToTextRequest) -> SpeechToTextResult: ...

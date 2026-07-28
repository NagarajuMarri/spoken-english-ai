from typing import Protocol
from pydantic import BaseModel, Field


class TextToSpeechRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    language: str = Field(default="en", max_length=20)
    voice_reference: str = Field(default="supportive-neutral", max_length=50)
    speaking_rate: float = Field(default=1, ge=0.5, le=2)
    learner_level: str = Field(max_length=30)
    correlation_id: str = Field(max_length=64)


class TextToSpeechResult(BaseModel):
    audio_asset_reference: str = Field(max_length=200)
    content_type: str
    duration_seconds: float = Field(ge=0)
    provider_job_id: str = Field(max_length=100)
    usage_units: int = Field(ge=0)
    generation_status: str


class TextToSpeechProvider(Protocol):
    def synthesize(self, request: TextToSpeechRequest) -> TextToSpeechResult: ...

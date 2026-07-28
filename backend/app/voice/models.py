from pydantic import BaseModel, Field


class VoiceTutorResult(BaseModel):
    voice_turn_id: str
    transcript: str = Field(max_length=4000)
    tutor_text: str = Field(max_length=2000)
    corrected_sentence: str | None = Field(default=None, max_length=2000)
    correction_explanation: str | None = Field(default=None, max_length=1000)
    vocabulary_suggestions: list[str] = Field(default_factory=list)
    pronunciation_summary: str | None = Field(default=None, max_length=500)
    fluency_summary: str | None = Field(default=None, max_length=500)
    confidence_encouragement: str = Field(max_length=300)
    next_question: str = Field(max_length=500)
    generated_audio_reference: str | None = Field(default=None, max_length=200)
    assessment_type: str | None = None
    processing_status: str
    degraded_features: list[str] = Field(default_factory=list)
    request_id: str | None = None
    correlation_id: str

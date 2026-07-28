from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class VoiceConsentUpdate(BaseModel):
    voice_processing_consent: bool
    audio_storage_consent: bool
    consent_version: str = Field(min_length=1, max_length=30)


class VoiceConsentRead(VoiceConsentUpdate):
    consented_at: datetime | None
    consent_withdrawn_at: datetime | None
    active: bool


class VoiceSessionCreate(BaseModel):
    learner_id: str
    scenario_id: str


class VoiceTurnCreate(BaseModel):
    simulated_audio_reference: str = Field(min_length=1, max_length=200)
    fake_transcript: str | None = Field(None, max_length=2000)
    media_type: str
    include_telugu_explanation: bool = False


class VoiceTurnRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    turn_number: int
    transcript: str
    tutor_text: str
    correction_summary: str | None
    synthetic_audio_reference: str
    pronunciation_assessment: dict[str, object] | None = None


class AudioAssetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    media_type: str
    storage_key: str
    status: str
    created_at: datetime
    expires_at: datetime | None
    deleted_at: datetime | None


class VoiceSessionRead(BaseModel):
    id: str
    learner_id: str
    scenario_id: str
    status: str
    created_at: datetime
    completed_at: datetime | None
    turns: list[VoiceTurnRead]
    audio_assets: list[AudioAssetRead]


class DailyPlanRead(BaseModel):
    selected_lesson: dict[str, object]
    recommended_scenario: str
    estimated_minutes: int
    current_streak: int
    recent_progress_summary: dict[str, object]
    voice_availability: bool
    consent_required: bool

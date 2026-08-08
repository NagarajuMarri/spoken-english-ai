from pydantic import BaseModel, Field, model_validator

from backend.app.domain.enums import LanguageMode


class TutorRead(BaseModel):
    tutor_id: str
    display_name: str
    gender: str
    avatar_profile: str
    voice_profile: str
    accent: str
    teaching_style: str
    animation_profile: str
    prompt_profile: str
    vocabulary_profile: str
    enabled: bool


class TutorPreferenceUpdate(BaseModel):
    tutor_id: str = Field(min_length=1, max_length=50)
    language_mode: LanguageMode | None = None
    telugu_explanations_enabled: bool | None = None

    @model_validator(mode="after")
    def normalize_legacy_preference(self):
        if self.language_mode is None:
            self.language_mode = (
                LanguageMode.ENGLISH_TELUGU
                if self.telugu_explanations_enabled
                else LanguageMode.ENGLISH
            )
        expected = self.language_mode != LanguageMode.ENGLISH
        if self.telugu_explanations_enabled is not None and self.telugu_explanations_enabled != expected:
            raise ValueError("Language mode conflicts with the legacy Telugu preference.")
        self.telugu_explanations_enabled = expected
        return self


class TutorPreferenceRead(BaseModel):
    learner_id: str
    tutor: TutorRead
    telugu_explanations_enabled: bool
    language_mode: LanguageMode


class LearnerDashboardRead(BaseModel):
    learner_id: str
    completed_sessions: int
    current_streak_days: int
    total_practice_minutes: int
    preferred_tutor_id: str
    subscription_tier: str
    subscription_status: str

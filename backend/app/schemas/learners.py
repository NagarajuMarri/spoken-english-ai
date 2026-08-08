from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from backend.app.domain.enums import LanguageMode, LearningGoal, NativeLanguage, ProficiencyLevel


class LearnerCreate(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=100)


class OnboardingUpdate(BaseModel):
    proficiency_level: ProficiencyLevel
    learning_goal: LearningGoal
    daily_goal_minutes: int = Field(ge=5, le=120)
    native_language: NativeLanguage
    preferred_tutor_id: str = Field(default="ananya", min_length=1, max_length=50)
    language_mode: LanguageMode | None = None
    telugu_explanations_enabled: bool | None = None

    @model_validator(mode="after")
    def normalize_language_mode(self):
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


class LearnerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: EmailStr
    display_name: str
    native_language: NativeLanguage
    proficiency_level: ProficiencyLevel
    learning_goal: LearningGoal
    daily_goal_minutes: int
    preferred_tutor_id: str
    telugu_explanations_enabled: bool
    language_mode: LanguageMode
    created_at: datetime
    updated_at: datetime

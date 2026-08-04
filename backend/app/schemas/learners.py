from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from backend.app.domain.enums import LearningGoal, NativeLanguage, ProficiencyLevel


class LearnerCreate(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=100)


class OnboardingUpdate(BaseModel):
    proficiency_level: ProficiencyLevel
    learning_goal: LearningGoal
    daily_goal_minutes: int = Field(ge=5, le=120)
    native_language: NativeLanguage
    preferred_tutor_id: str = Field(default="ananya", min_length=1, max_length=50)
    telugu_explanations_enabled: bool = False


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
    created_at: datetime
    updated_at: datetime

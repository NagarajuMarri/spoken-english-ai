from pydantic import BaseModel, Field


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
    telugu_explanations_enabled: bool = False


class TutorPreferenceRead(BaseModel):
    learner_id: str
    tutor: TutorRead
    telugu_explanations_enabled: bool


class LearnerDashboardRead(BaseModel):
    learner_id: str
    completed_sessions: int
    current_streak_days: int
    total_practice_minutes: int
    preferred_tutor_id: str
    subscription_tier: str
    subscription_status: str

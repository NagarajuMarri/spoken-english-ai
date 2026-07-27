from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from backend.app.domain.enums import LessonSessionStatus, ProficiencyLevel


class CurriculumLessonRead(BaseModel):
    id: str
    title: str
    proficiency_level: ProficiencyLevel
    scenario_id: str
    learning_objectives: tuple[str, ...]
    target_vocabulary: tuple[str, ...]
    grammar_focus: tuple[str, ...]
    estimated_duration_minutes: int
    completion_criteria: str


class LessonSessionCreate(BaseModel):
    learner_id: str
    lesson_id: str
    conversation_id: str | None = None


class EvaluationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    grammar_score: int = Field(ge=0, le=100)
    vocabulary_score: int = Field(ge=0, le=100)
    fluency_score: int = Field(ge=0, le=100)
    task_completion_score: int = Field(ge=0, le=100)
    confidence_score: int = Field(ge=0, le=100)
    overall_score: int = Field(ge=0, le=100)
    strengths: list[str]
    priority_improvements: list[str]
    corrected_examples: list[str]


class LessonComplete(BaseModel):
    duration_seconds: int = Field(ge=0, le=86400)


class LessonSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    learner_id: str
    lesson_id: str
    conversation_id: str | None
    status: LessonSessionStatus
    started_at: datetime
    completed_at: datetime | None
    duration_seconds: int
    evaluation: EvaluationRead | None


class ProgressRead(BaseModel):
    completed_lessons: int
    completed_conversations: int
    total_practice_minutes: float
    average_score: float | None
    progress_by_scenario: dict[str, int]
    progress_by_proficiency_level: dict[str, int]


class StreakRead(BaseModel):
    current_streak: int
    longest_streak: int
    last_practice_date: str | None
    timezone: str = "UTC"

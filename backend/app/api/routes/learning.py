from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from backend.app.core.errors import AppError
from backend.app.db.session import get_db
from backend.app.domain.curriculum import LESSONS, LESSONS_BY_ID
from backend.app.domain.enums import ProficiencyLevel
from backend.app.schemas.curriculum import CurriculumLessonRead, LessonComplete, LessonSessionCreate, LessonSessionRead, ProgressRead, StreakRead
from backend.app.services.learning import LearningService

router = APIRouter(prefix="/api/v1", tags=["learning"])


@router.get("/curriculum/levels", response_model=list[ProficiencyLevel])
def levels():
    return list(ProficiencyLevel)


@router.get("/curriculum/lessons", response_model=list[CurriculumLessonRead])
def lessons(proficiency_level: ProficiencyLevel | None = Query(None), scenario_id: str | None = Query(None)):
    result = LESSONS
    if proficiency_level:
        result = tuple(item for item in result if item.proficiency_level == proficiency_level)
    if scenario_id:
        result = tuple(item for item in result if item.scenario_id == scenario_id)
    return result


@router.get("/curriculum/lessons/{lesson_id}", response_model=CurriculumLessonRead)
def lesson(lesson_id: str):
    item = LESSONS_BY_ID.get(lesson_id)
    if item is None:
        raise AppError(status.HTTP_404_NOT_FOUND, "lesson_not_found", "Lesson not found.")
    return item


@router.get("/learners/{learner_id}/daily-lesson", response_model=CurriculumLessonRead)
def daily_lesson(learner_id: str, session: Session = Depends(get_db)):
    return LearningService(session).daily_lesson(learner_id)


@router.post("/lesson-sessions", response_model=LessonSessionRead, status_code=status.HTTP_201_CREATED)
def create_lesson_session(data: LessonSessionCreate, session: Session = Depends(get_db)):
    return LearningService(session).create_session(data.learner_id, data.lesson_id, data.conversation_id)


@router.get("/lesson-sessions/{session_id}", response_model=LessonSessionRead)
def get_lesson_session(session_id: str, session: Session = Depends(get_db)):
    return LearningService(session).get_session(session_id)


@router.post("/lesson-sessions/{session_id}/complete", response_model=LessonSessionRead)
def complete_lesson_session(session_id: str, data: LessonComplete, session: Session = Depends(get_db)):
    return LearningService(session).complete(session_id, data.duration_seconds)


@router.get("/learners/{learner_id}/progress", response_model=ProgressRead)
def progress(learner_id: str, session: Session = Depends(get_db)):
    return LearningService(session).progress(learner_id)


@router.get("/learners/{learner_id}/streak", response_model=StreakRead)
def streak(learner_id: str, session: Session = Depends(get_db)):
    return LearningService(session).streak(learner_id)

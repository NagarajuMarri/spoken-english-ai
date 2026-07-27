from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from backend.app.models import Conversation, ConversationEvaluation, LessonSession, ProgressRecord


class LearningRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def completed_lesson_ids(self, learner_id: str) -> list[str]:
        return list(self.session.scalars(select(LessonSession.lesson_id).where(
            LessonSession.learner_id == learner_id, LessonSession.status == "COMPLETED"
        )))

    def recent_lesson_ids(self, learner_id: str, limit: int = 3) -> list[str]:
        return list(self.session.scalars(
            select(LessonSession.lesson_id).where(LessonSession.learner_id == learner_id)
            .order_by(LessonSession.started_at.desc()).limit(limit)
        ))

    def create_session(self, learner_id, lesson_id, conversation_id):
        item = LessonSession(learner_id=learner_id, lesson_id=lesson_id, conversation_id=conversation_id)
        self.session.add(item)
        self.session.commit()
        return self.get_session(item.id)

    def get_session(self, session_id):
        return self.session.scalar(
            select(LessonSession).options(selectinload(LessonSession.evaluation))
            .where(LessonSession.id == session_id)
        )

    def complete(self, lesson_session, duration_seconds, result, lesson):
        now = datetime.now(timezone.utc)
        lesson_session.status = "COMPLETED"
        lesson_session.completed_at = now
        lesson_session.duration_seconds = duration_seconds
        evaluation = ConversationEvaluation(lesson_session_id=lesson_session.id, **result.__dict__)
        self.session.add(evaluation)
        self.session.add(ProgressRecord(
            learner_id=lesson_session.learner_id,
            conversation_id=lesson_session.conversation_id,
            lesson_id=lesson.id,
            practice_date=now.date(),
            duration_seconds=duration_seconds,
            score=result.overall_score,
            scenario_id=lesson.scenario_id,
            proficiency_level=lesson.proficiency_level.value,
        ))
        self.session.commit()
        self.session.expire_all()
        return self.get_session(lesson_session.id)

    def progress_records(self, learner_id):
        return list(self.session.scalars(
            select(ProgressRecord).where(ProgressRecord.learner_id == learner_id)
            .order_by(ProgressRecord.practice_date)
        ))

    def completed_conversation_count(self, learner_id):
        return self.session.scalar(
            select(func.count(Conversation.id)).where(Conversation.learner_id == learner_id)
        ) or 0

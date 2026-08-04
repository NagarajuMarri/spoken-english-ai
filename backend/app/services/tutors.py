from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.errors import AppError
from backend.app.models.entities import Learner, ProgressRecord
from backend.app.tutors import TUTORS, get_tutor


class TutorExperienceService:
    def __init__(self, session: Session):
        self.session = session

    @staticmethod
    def catalogue() -> list[dict[str, str | bool]]:
        return [tutor.public_dict() for tutor in TUTORS if tutor.enabled]

    def preference(self, learner: Learner) -> dict:
        tutor = self._selected_tutor(learner)
        return {
            "learner_id": learner.id,
            "tutor": tutor.public_dict(),
            "telugu_explanations_enabled": learner.telugu_explanations_enabled,
        }

    def update_preference(
        self, learner: Learner, tutor_id: str, telugu_explanations_enabled: bool
    ) -> dict:
        try:
            tutor = get_tutor(tutor_id)
        except KeyError as error:
            raise AppError(422, "unknown_tutor", "Select an enabled tutor.") from error
        learner.preferred_tutor_id = tutor.tutor_id
        learner.telugu_explanations_enabled = telugu_explanations_enabled
        self.session.commit()
        self.session.refresh(learner)
        return self.preference(learner)

    def dashboard(self, learner: Learner) -> dict:
        records = list(self.session.scalars(
            select(ProgressRecord).where(ProgressRecord.learner_id == learner.id)
        ))
        dates = {record.practice_date for record in records if record.practice_date is not None}
        return {
            "learner_id": learner.id,
            "completed_sessions": len(records),
            "current_streak_days": self._streak(dates),
            "total_practice_minutes": sum(record.duration_seconds for record in records) // 60,
            "preferred_tutor_id": self._selected_tutor(learner).tutor_id,
            "subscription_tier": "FREE",
            "subscription_status": "READY_FOR_PROVIDER_INTEGRATION",
        }

    @staticmethod
    def _selected_tutor(learner: Learner):
        try:
            return get_tutor(learner.preferred_tutor_id or "ananya")
        except KeyError:
            return get_tutor("ananya")

    @staticmethod
    def _streak(dates: set[date]) -> int:
        if not dates:
            return 0
        cursor = max(dates)
        streak = 0
        while cursor in dates:
            streak += 1
            cursor -= timedelta(days=1)
        return streak

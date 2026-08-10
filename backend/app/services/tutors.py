from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.errors import AppError
from backend.app.models.entities import Learner, ProgressRecord
from backend.app.tutors import TUTORS, get_tutor
from backend.app.domain.enums import LanguageMode


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
            "language_mode": learner.language_mode,
        }

    def update_preference(
        self, learner: Learner, tutor_id: str, language_mode: LanguageMode
    ) -> dict:
        try:
            tutor = get_tutor(tutor_id)
        except KeyError as error:
            raise AppError(422, "unknown_tutor", "Select an enabled tutor.") from error
        learner.preferred_tutor_id = tutor.tutor_id
        learner.language_mode = language_mode.value
        learner.telugu_explanations_enabled = language_mode != LanguageMode.ENGLISH
        self.session.commit()
        self.session.refresh(learner)
        return self.preference(learner)

    def dashboard(
        self,
        learner: Learner,
        *,
        subscription_tier: str,
        subscription_status: str,
    ) -> dict:
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
            "subscription_tier": subscription_tier,
            "subscription_status": subscription_status,
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
        today = datetime.now(timezone.utc).date()
        if cursor not in {today, today - timedelta(days=1)}:
            return 0
        streak = 0
        while cursor in dates:
            streak += 1
            cursor -= timedelta(days=1)
        return streak

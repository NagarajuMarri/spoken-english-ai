from datetime import datetime, timezone
from sqlalchemy import delete, select

from backend.app.models import LearnerMemoryProfile, LearnerMemorySignal


class ConversationMemoryRepository:
    def __init__(self, session):
        self.session = session

    def profile(self, learner_id):
        profile = self.session.scalar(select(LearnerMemoryProfile).where(
            LearnerMemoryProfile.learner_id == learner_id
        ))
        if profile is None:
            profile = LearnerMemoryProfile(learner_id=learner_id)
            self.session.add(profile)
            self.session.flush()
        return profile

    def signals(self, learner_id):
        return list(self.session.scalars(select(LearnerMemorySignal).where(
            LearnerMemorySignal.learner_id == learner_id
        ).order_by(LearnerMemorySignal.category, LearnerMemorySignal.normalised_value)))

    def upsert_signal(self, learner_id, signal):
        normalised = " ".join(signal.value.casefold().split())
        item = self.session.scalar(select(LearnerMemorySignal).where(
            LearnerMemorySignal.learner_id == learner_id,
            LearnerMemorySignal.category == signal.category,
            LearnerMemorySignal.normalised_value == normalised,
        ))
        if item is None:
            item = LearnerMemorySignal(
                learner_id=learner_id, category=signal.category,
                normalised_value=normalised, display_value=signal.value.strip(),
                trend_value=signal.trend_value,
            )
            self.session.add(item)
        else:
            item.occurrence_count += 1
            item.last_observed_at = datetime.now(timezone.utc)
            item.trend_value = signal.trend_value if signal.trend_value is not None else item.trend_value
        return item

    def delete_all(self, learner_id):
        count = len(self.signals(learner_id))
        self.session.execute(delete(LearnerMemorySignal).where(LearnerMemorySignal.learner_id == learner_id))
        self.session.execute(delete(LearnerMemoryProfile).where(LearnerMemoryProfile.learner_id == learner_id))
        return count

from collections import Counter
from datetime import date, timedelta
from fastapi import status
from sqlalchemy.orm import Session

from backend.app.core.errors import AppError
from backend.app.domain.curriculum import LESSONS_BY_ID, select_daily_lesson
from backend.app.integrations.llm import RuleBasedLLMProvider
from backend.app.repositories.conversations import ConversationRepository
from backend.app.repositories.learning import LearningRepository
from backend.app.repositories.learners import LearnerRepository


class LearningService:
    def __init__(self, session: Session, provider=None) -> None:
        self.session = session
        self.repository = LearningRepository(session)
        self.learners = LearnerRepository(session)
        self.provider = provider or RuleBasedLLMProvider()

    def _learner(self, learner_id):
        learner = self.learners.get(learner_id)
        if learner is None:
            raise AppError(status.HTTP_404_NOT_FOUND, "learner_not_found", "Learner not found.")
        return learner

    def daily_lesson(self, learner_id, current_date=None):
        learner = self._learner(learner_id)
        from backend.app.domain.enums import LearningGoal, ProficiencyLevel
        return select_daily_lesson(
            ProficiencyLevel(learner.proficiency_level),
            LearningGoal(learner.learning_goal),
            set(self.repository.completed_lesson_ids(learner_id)),
            set(self.repository.recent_lesson_ids(learner_id)),
            current_date or date.today(),
        )

    def create_session(self, learner_id, lesson_id, conversation_id=None):
        self._learner(learner_id)
        if lesson_id not in LESSONS_BY_ID:
            raise AppError(status.HTTP_404_NOT_FOUND, "lesson_not_found", "Lesson not found.")
        if conversation_id:
            conversation = ConversationRepository(self.session).get(conversation_id)
            if conversation is None or conversation.learner_id != learner_id:
                raise AppError(status.HTTP_404_NOT_FOUND, "conversation_not_found", "Conversation not found.")
        return self.repository.create_session(learner_id, lesson_id, conversation_id)

    def get_session(self, session_id):
        item = self.repository.get_session(session_id)
        if item is None:
            raise AppError(status.HTTP_404_NOT_FOUND, "lesson_session_not_found", "Lesson session not found.")
        return item

    def complete(self, session_id, duration_seconds):
        item = self.get_session(session_id)
        if item.status == "COMPLETED":
            return item
        messages = []
        if item.conversation_id:
            conversation = ConversationRepository(self.session).get(item.conversation_id)
            messages = conversation.messages if conversation else []
        result = self.provider.evaluate_conversation(messages)
        return self.repository.complete(item, duration_seconds, result, LESSONS_BY_ID[item.lesson_id])

    def progress(self, learner_id):
        self._learner(learner_id)
        records = [item for item in self.repository.progress_records(learner_id) if item.lesson_id]
        scores = [item.score for item in records if item.score is not None]
        return {
            "completed_lessons": len(records),
            "completed_conversations": self.repository.completed_conversation_count(learner_id),
            "total_practice_minutes": round(sum(item.duration_seconds for item in records) / 60, 2),
            "average_score": round(sum(scores) / len(scores), 2) if scores else None,
            "progress_by_scenario": dict(Counter(item.scenario_id for item in records if item.scenario_id)),
            "progress_by_proficiency_level": dict(Counter(item.proficiency_level for item in records if item.proficiency_level)),
        }

    def streak(self, learner_id, today=None):
        self._learner(learner_id)
        days = sorted({item.practice_date for item in self.repository.progress_records(learner_id) if item.lesson_id and item.practice_date})
        if not days:
            return {"current_streak": 0, "longest_streak": 0, "last_practice_date": None, "timezone": "UTC"}
        longest = run = 1
        for previous, current in zip(days, days[1:]):
            run = run + 1 if current == previous + timedelta(days=1) else 1
            longest = max(longest, run)
        today = today or date.today()
        current = 0
        if days[-1] in {today, today - timedelta(days=1)}:
            current = 1
            for previous, current_day in zip(reversed(days[:-1]), reversed(days[1:])):
                if current_day == previous + timedelta(days=1):
                    current += 1
                else:
                    break
        return {"current_streak": current, "longest_streak": longest, "last_practice_date": days[-1].isoformat(), "timezone": "UTC"}

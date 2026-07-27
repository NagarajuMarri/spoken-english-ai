from fastapi import status
from sqlalchemy.orm import Session

from backend.app.core.errors import AppError
from backend.app.domain.scenarios import SCENARIOS_BY_ID
from backend.app.domain.tutor import respond
from backend.app.repositories.conversations import ConversationRepository
from backend.app.repositories.learners import LearnerRepository


class ConversationService:
    def __init__(self, session: Session) -> None:
        self.repository = ConversationRepository(session)
        self.learners = LearnerRepository(session)

    def create(self, learner_id: str, scenario_id: str):
        if self.learners.get(learner_id) is None:
            raise AppError(status.HTTP_404_NOT_FOUND, "learner_not_found", "Learner not found.")
        if scenario_id not in SCENARIOS_BY_ID:
            raise AppError(status.HTTP_404_NOT_FOUND, "scenario_not_found", "Scenario not found.")
        return self.repository.create(learner_id, scenario_id)

    def get(self, conversation_id: str):
        conversation = self.repository.get(conversation_id)
        if conversation is None:
            raise AppError(
                status.HTTP_404_NOT_FOUND, "conversation_not_found", "Conversation not found."
            )
        return conversation

    def add_message(self, conversation_id: str, text: str, include_telugu: bool):
        self.get(conversation_id)
        cleaned = text.strip()
        if not cleaned:
            raise AppError(status.HTTP_422_UNPROCESSABLE_ENTITY, "empty_message", "Message cannot be empty.")
        tutor_turn = respond(cleaned, include_telugu)
        return self.repository.add_message(
            conversation_id, text, tutor_turn.response, tutor_turn.correction
        )

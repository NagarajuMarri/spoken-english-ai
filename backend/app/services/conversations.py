from fastapi import status
from sqlalchemy.orm import Session

from backend.app.core.errors import AppError
from backend.app.domain.scenarios import SCENARIOS_BY_ID
from backend.app.integrations.llm import RuleBasedLLMProvider
from backend.app.repositories.ai_turns import AITurnAttemptRepository
from backend.app.repositories.conversations import ConversationRepository, TurnSequenceConflict
from backend.app.repositories.learners import LearnerRepository
from backend.app.unicode_safety import (
    UnicodeSafetyError,
    normalize_input_text,
    normalize_output_text,
)


class ConversationService:
    def __init__(self, session: Session, provider=None) -> None:
        self.session = session
        self.repository = ConversationRepository(session)
        self.ai_turns = AITurnAttemptRepository(session)
        self.learners = LearnerRepository(session)
        self.provider = provider or RuleBasedLLMProvider()

    def create(self, learner_id: str, scenario_id: str):
        learner = self.learners.get(learner_id)
        if learner is None:
            raise AppError(status.HTTP_404_NOT_FOUND, "learner_not_found", "Learner not found.")
        if scenario_id not in SCENARIOS_BY_ID:
            raise AppError(status.HTTP_404_NOT_FOUND, "scenario_not_found", "Scenario not found.")
        try:
            conversation = self.repository.create(learner_id, scenario_id, commit=False)
            opening = self.ai_turns.create_opening(
                conversation_id=conversation.id,
                learner_id=learner_id,
                spoken_text=SCENARIOS_BY_ID[scenario_id].opening_prompt,
                language_mode=learner.language_mode or "ENGLISH",
                commit=False,
            )
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        self.session.refresh(conversation)
        self.session.refresh(opening)
        return conversation, opening

    def opening(self, conversation_id: str):
        return self.ai_turns.opening(conversation_id)

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
        try:
            cleaned = normalize_input_text(cleaned)
        except UnicodeSafetyError as exc:
            raise AppError(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "invalid_learner_message",
                "The learner message contains unsupported or malformed text.",
                retryable=False,
            ) from exc
        tutor_turn = self.provider.generate_tutor_response(cleaned, include_telugu)
        try:
            tutor_response = normalize_output_text(
                tutor_turn.response,
                allow_telugu=include_telugu,
            )
            correction = (
                normalize_output_text(
                    tutor_turn.correction,
                    allow_telugu=include_telugu,
                )
                if tutor_turn.correction is not None
                else None
            )
        except UnicodeSafetyError as exc:
            raise AppError(
                status.HTTP_502_BAD_GATEWAY,
                "invalid_tutor_output",
                "The tutor response could not be validated.",
                retryable=False,
            ) from exc
        try:
            return self.repository.add_message(
                conversation_id, cleaned, tutor_response, correction
            )
        except TurnSequenceConflict as exc:
            raise AppError(
                status.HTTP_409_CONFLICT,
                "turn_sequence_conflict",
                "The conversation changed concurrently; retry the message.",
            ) from exc

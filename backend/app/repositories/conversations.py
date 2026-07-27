from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from backend.app.models import Conversation, ConversationMessage, ProgressRecord


class TurnSequenceConflict(Exception):
    pass


class ConversationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, learner_id: str, scenario_id: str) -> Conversation:
        conversation = Conversation(learner_id=learner_id, scenario_id=scenario_id)
        self.session.add(conversation)
        self.session.commit()
        self.session.refresh(conversation)
        return conversation

    def get(self, conversation_id: str) -> Conversation | None:
        statement = (
            select(Conversation)
            .options(selectinload(Conversation.messages))
            .where(Conversation.id == conversation_id)
        )
        return self.session.scalar(statement)

    def add_message(
        self,
        conversation_id: str,
        learner_text: str,
        tutor_response: str,
        correction_summary: str | None,
    ) -> ConversationMessage:
        for attempt in range(3):
            conversation = self.session.scalar(
                select(Conversation).where(Conversation.id == conversation_id).with_for_update()
            )
            turn = self.session.scalar(
                select(func.max(ConversationMessage.turn_number)).where(
                    ConversationMessage.conversation_id == conversation_id
                )
            ) or 0
            message = ConversationMessage(
                conversation_id=conversation_id,
                turn_number=turn + 1,
                learner_text=learner_text,
                tutor_response=tutor_response,
                correction_summary=correction_summary,
            )
            self.session.add(message)
            self.session.add(
                ProgressRecord(
                    learner_id=conversation.learner_id,
                    conversation_id=conversation_id,
                    completed_turns=turn + 1,
                )
            )
            try:
                self.session.commit()
            except IntegrityError as exc:
                self.session.rollback()
                if attempt == 2:
                    raise TurnSequenceConflict from exc
                continue
            self.session.refresh(message)
            return message
        raise TurnSequenceConflict

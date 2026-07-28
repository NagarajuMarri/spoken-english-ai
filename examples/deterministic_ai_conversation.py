from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.ai.deterministic_provider import DeterministicAIProvider
from backend.app.ai.models import AIConversationRequest
from backend.app.ai.service import AIConversationService
from backend.app.conversation_memory.models import MemorySignalInput
from backend.app.conversation_memory.service import ConversationMemoryService
from backend.app.db.base import Base
from backend.app.models import Conversation, Learner, UserAccount


def main():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        user = UserAccount(email="demo@example.invalid", password_hash="not-a-real-password-hash")
        session.add(user)
        session.flush()
        learner = Learner(user_account_id=user.id, email=user.email, display_name="Demo Learner")
        session.add(learner)
        session.flush()
        conversation = Conversation(learner_id=learner.id, scenario_id="travel")
        session.add(conversation)
        session.commit()
        response = AIConversationService(DeterministicAIProvider()).generate(AIConversationRequest(
            learner_id=learner.id, conversation_id=conversation.id,
            learner_level=learner.proficiency_level, scenario="travel",
            topic="At the airport", current_learner_message="i travel tomorrow",
            correlation_id="example-ai",
        ))
        ConversationMemoryService(session).update(learner.id, [
            MemorySignalInput(category="grammar", value=value)
            for value in response.learning_signals.grammar_focus
        ])
        print("Tutor:", response.tutor_message)
        print("Correction:", response.corrected_learner_sentence)
        print("Vocabulary:", ", ".join(response.vocabulary_suggestions))
        print("Next:", response.conversation_question)
    engine.dispose()


if __name__ == "__main__":
    main()

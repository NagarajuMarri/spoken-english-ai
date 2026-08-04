from backend.app.conversation_memory.repository import ConversationMemoryRepository


class ConversationMemoryService:
    def __init__(self, session):
        self.session = session
        self.repository = ConversationMemoryRepository(session)

    def update(self, learner_id, signals):
        self.repository.profile(learner_id)
        items = [self.repository.upsert_signal(learner_id, signal) for signal in signals]
        self.session.commit()
        return items

    def export(self, learner_id):
        profile = self.repository.profile(learner_id)
        signals = self.repository.signals(learner_id)
        self.session.commit()
        return {
            "schema_version": profile.schema_version,
            "current_level": profile.current_level,
            "preferred_topics": profile.preferred_topics,
            "avoided_topics": profile.avoided_topics,
            "signals": [
                {"category": item.category, "value": item.display_value, "occurrences": item.occurrence_count}
                for item in signals
            ],
        }

    def delete(self, learner_id):
        count = self.repository.delete_all(learner_id)
        self.session.commit()
        return count

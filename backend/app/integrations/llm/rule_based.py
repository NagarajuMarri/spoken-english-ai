from backend.app.domain.evaluation import evaluate
from backend.app.domain.tutor import respond


class RuleBasedLLMProvider:
    def generate_tutor_response(self, text, include_telugu_explanation=False):
        return respond(text, include_telugu_explanation)

    def evaluate_conversation(self, messages):
        return evaluate(messages)

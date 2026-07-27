from collections.abc import Sequence

from backend.app.domain.evaluation import EvaluationResult
from backend.app.domain.evaluation import evaluate
from backend.app.domain.tutor import TutorTurn, respond


class RuleBasedLLMProvider:
    def generate_tutor_response(
        self, text: str, include_telugu_explanation: bool = False
    ) -> TutorTurn:
        return respond(text, include_telugu_explanation)

    def evaluate_conversation(self, messages: Sequence[object]) -> EvaluationResult:
        return evaluate(messages)

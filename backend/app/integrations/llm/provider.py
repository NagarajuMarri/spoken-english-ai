from collections.abc import Sequence
from typing import Protocol

from backend.app.domain.evaluation import EvaluationResult
from backend.app.domain.tutor import TutorTurn


class LLMProvider(Protocol):
    def generate_tutor_response(self, text: str, include_telugu_explanation: bool = False) -> TutorTurn: ...
    def evaluate_conversation(self, messages: Sequence[object]) -> EvaluationResult: ...

from dataclasses import dataclass

from backend.app.ai.validation import validate_provider_output


@dataclass(frozen=True)
class AdaptivePolicy:
    difficulty: str
    correction_frequency: str
    response_length: int
    vocabulary_complexity: str
    grammar_focus: str
    speaking_rate: float
    revision_needed: bool

    @classmethod
    def decide(cls, *, level: str, correctness: float, repeated_mistakes: int, confidence: int):
        struggling = correctness < 0.5 or repeated_mistakes >= 3
        excelling = correctness >= 0.85 and confidence >= 70
        return cls(
            difficulty="decrease" if struggling else ("challenge" if excelling else "maintain"),
            correction_frequency="focused" if struggling else "light",
            response_length=180 if struggling else 300,
            vocabulary_complexity="simple" if struggling else ("expanded" if excelling else "level"),
            grammar_focus="repeated_pattern" if repeated_mistakes else "current_lesson",
            speaking_rate=0.85 if struggling else 1.0,
            revision_needed=struggling,
        )


class AIConversationService:
    def __init__(self, provider):
        self.provider = provider

    def generate(self, request):
        return validate_provider_output(self.provider.generate(request))

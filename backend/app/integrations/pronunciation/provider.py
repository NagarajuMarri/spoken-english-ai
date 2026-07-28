from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class PronunciationAssessment:
    assessment_type: str
    synthetic_score: int
    note: str


class PronunciationAssessmentProvider(Protocol):
    def assess(self, transcript: str) -> PronunciationAssessment: ...


class FakePronunciationAssessmentProvider:
    def assess(self, transcript: str) -> PronunciationAssessment:
        score = min(100, 40 + len(transcript.split()) * 5)
        return PronunciationAssessment(
            assessment_type="synthetic_test_double",
            synthetic_score=score,
            note="Synthetic test data; not a real pronunciation assessment.",
        )

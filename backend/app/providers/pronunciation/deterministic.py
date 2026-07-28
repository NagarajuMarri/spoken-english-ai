from backend.app.providers.pronunciation.contracts import PronunciationResult


class DeterministicPronunciationProvider:
    name = "deterministic-pronunciation"

    def assess(self, request):
        score = min(90, 55 + len(request.learner_transcript.split()))
        return PronunciationResult(
            assessment_type="SYNTHETIC_NOT_ACOUSTIC",
            overall_score=score,
            word_accuracy=score,
            fluency_score=max(0, score - 4),
            completeness_score=100,
            pronunciation_score=score,
            confidence_score=70,
            word_level_feedback=[],
            improvement_tips=["Use a steady pace.", "Practise one phrase at a time."],
            provider_metadata_reference="deterministic:synthetic:v1",
        )

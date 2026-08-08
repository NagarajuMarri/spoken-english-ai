from backend.app.ai.models import UsageInfo
from backend.app.language_review.models import (
    ExpressionHint,
    LanguageMode,
    LanguageReviewResult,
    ReviewReasonCode,
)


class DeterministicLanguageReviewProvider:
    name = "test-only-native-telugu-review"

    def review(self, request):
        terms = request.required_learning_terms
        term_text = " ".join(terms)
        if request.language_mode == LanguageMode.TELUGU_DOMINANT:
            final_text = f"చాలా బాగా ప్రయత్నించారు. {term_text} గురించి ఇప్పుడు సులభంగా చూద్దాం.".strip()
            explanation = "ఈ sentence లో అవసరమైన భాగాన్ని మాత్రమే మార్చాలి. అర్థం మాత్రం అలాగే ఉంటుంది."
            question = "ఇప్పుడు ఇదే విషయాన్ని మీ మాటల్లో ఇంకోసారి చెబుతారా?"
            reason = ReviewReasonCode.NATURALIZED_TELUGU
        else:
            final_text = f"Good try! ఈసారి {term_text} కొంచెం సహజంగా వాడుదాం.".strip()
            explanation = "ఈ sentence లో చిన్న correction చాలు; మీరు చెప్పాలనుకున్న meaning సరైనదే."
            question = "ఇప్పుడు అదే sentence ని ఇంకోసారి English లో చెబుతారా?"
            reason = ReviewReasonCode.IMPROVED_CODE_SWITCHING
        return LanguageReviewResult(
            final_text=final_text,
            final_correction_explanation=explanation if request.source_correction_explanation else None,
            final_conversation_question=question,
            final_encouragement="బాగా చేస్తున్నారు—ఇలాగే practice కొనసాగించండి.",
            language_mode=request.language_mode,
            review_changed=True,
            review_reason_code=reason,
            preserved_learning_terms=terms,
            expression_hint=(
                ExpressionHint.CORRECTIVE
                if request.source_correction_explanation
                else ExpressionHint.ENCOURAGING
            ),
            source_content_digest=request.source_content_digest,
            provider_metadata_reference="language-review:deterministic:v1",
            usage=UsageInfo(input_units=20, output_units=30, provider_requests=1),
        )

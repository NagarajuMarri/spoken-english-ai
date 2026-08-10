import hashlib
import json
import re

from backend.app.ai.exceptions import ProviderConfigurationError, ProviderOutputInvalid
from backend.app.ai.models import AIConversationResponse, UsageInfo
from backend.app.language_review.models import (
    ExpressionHint,
    LanguageReviewStatus,
    LanguageMode,
    LanguageReviewRequest,
    LanguageReviewResult,
    ReviewReasonCode,
)
from backend.app.unicode_safety import UnicodeSafetyError, normalize_output_text


LEARNING_TERM_ALLOWLIST = {
    "grammar", "tense", "sentence", "verb", "noun", "pronunciation",
    "confidence", "fluency", "practice",
}


def protected_content_digest(
    response: AIConversationResponse,
    *,
    learning_objective: str,
) -> str:
    protected = {
        "corrected_learner_sentence": response.corrected_learner_sentence,
        "grammar_feedback": response.grammar_feedback,
        "vocabulary_suggestions": response.vocabulary_suggestions,
        "detected_level": response.detected_level,
        "recommended_next_difficulty": response.recommended_next_difficulty,
        "learning_signals": response.learning_signals.model_dump(mode="json"),
        "learning_objective": learning_objective,
    }
    encoded = json.dumps(protected, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def _terms_in(*values: str | None) -> list[str]:
    joined = " ".join(value or "" for value in values).lower()
    words = set(re.findall(r"[a-z]+", joined))
    return sorted(term for term in LEARNING_TERM_ALLOWLIST if term in words)


def build_review_request(
    response: AIConversationResponse,
    *,
    language_mode: LanguageMode,
    learning_objective: str,
    learner_level: str,
    correlation_id: str,
) -> LanguageReviewRequest:
    return LanguageReviewRequest(
        source_tutor_message=response.tutor_message,
        source_correction_explanation=response.correction_explanation,
        source_conversation_question=response.conversation_question,
        source_encouragement=response.encouragement,
        corrected_learner_sentence=response.corrected_learner_sentence,
        grammar_feedback=response.grammar_feedback,
        vocabulary_suggestions=response.vocabulary_suggestions,
        learning_objective=learning_objective,
        learner_level=learner_level,
        language_mode=language_mode,
        required_learning_terms=_terms_in(
            response.tutor_message,
            response.correction_explanation,
            response.conversation_question,
            response.encouragement,
        ),
        source_content_digest=protected_content_digest(
            response,
            learning_objective=learning_objective,
        ),
        correlation_id=correlation_id,
    )


def _validate_result(request: LanguageReviewRequest, result: LanguageReviewResult) -> None:
    if result.language_mode != request.language_mode:
        raise ProviderOutputInvalid("Language reviewer changed the requested mode.", schema_path="language_mode")
    if result.source_content_digest != request.source_content_digest:
        raise ProviderOutputInvalid("Language reviewer lost the protected content binding.", schema_path="source_content_digest")
    combined = " ".join(filter(None, (
        result.final_text,
        result.final_correction_explanation,
        result.final_conversation_question,
        result.final_encouragement,
    ))).lower()
    combined_words = set(re.findall(r"[a-z]+", combined))
    has_telugu = any("\u0c00" <= character <= "\u0c7f" for character in combined)
    has_english = bool(combined_words)
    if result.preserved_learning_terms != request.required_learning_terms:
        raise ProviderOutputInvalid("Application-controlled learning terms changed.", schema_path="protected_learning_terms")
    if any(term not in combined_words for term in request.required_learning_terms):
        raise ProviderOutputInvalid("Language reviewer dropped a required learning term.", schema_path="preserved_learning_terms")
    source_fields = (
        request.source_tutor_message,
        request.source_correction_explanation,
        request.source_conversation_question,
        request.source_encouragement,
    )
    result_fields = (
        result.final_text,
        result.final_correction_explanation,
        result.final_conversation_question,
        result.final_encouragement,
    )
    fields_changed = result_fields != source_fields
    if result.review_changed != fields_changed:
        raise ProviderOutputInvalid(
            "Language reviewer reported an inconsistent change status.",
            schema_path="review_changed",
        )
    if fields_changed == (result.review_reason_code == ReviewReasonCode.NOT_REQUIRED):
        raise ProviderOutputInvalid(
            "Language reviewer reported an inconsistent reason code.",
            schema_path="review_reason_code",
        )
    if request.language_mode != LanguageMode.ENGLISH and not has_telugu:
        raise ProviderOutputInvalid(
            "Telugu review output did not contain Telugu.",
            schema_path="final_text",
        )
    if request.language_mode == LanguageMode.ENGLISH_TELUGU and not has_english:
        raise ProviderOutputInvalid(
            "English and Telugu mode did not retain English.",
            schema_path="final_text",
        )
    if request.language_mode == LanguageMode.ENGLISH:
        if result_fields != source_fields:
            raise ProviderOutputInvalid("English mode must remain an exact presentation pass-through.", schema_path="final_text")


def _normalize_result_output(result: LanguageReviewResult) -> LanguageReviewResult:
    allow_telugu = result.language_mode != LanguageMode.ENGLISH
    updates: dict[str, object] = {}
    path = "root"
    try:
        for field in (
            "final_text",
            "final_correction_explanation",
            "final_conversation_question",
            "final_encouragement",
        ):
            path = field
            value = getattr(result, field)
            if value is not None:
                updates[field] = normalize_output_text(
                    value,
                    allow_telugu=allow_telugu,
                )
        normalized_terms = []
        for index, item in enumerate(result.preserved_learning_terms):
            path = f"preserved_learning_terms.{index}"
            normalized_terms.append(normalize_output_text(item, allow_telugu=allow_telugu))
        updates["preserved_learning_terms"] = normalized_terms
    except UnicodeSafetyError as exc:
        raise ProviderOutputInvalid(
            "Language review output failed Unicode or script validation.",
            schema_path=path,
        ) from exc
    return result.model_copy(update=updates)


class LanguageReviewService:
    def __init__(self, provider):
        self.provider = provider

    def review(
        self,
        response: AIConversationResponse,
        *,
        language_mode: LanguageMode,
        learning_objective: str,
        learner_level: str,
        correlation_id: str,
    ) -> tuple[AIConversationResponse, LanguageReviewResult]:
        request = build_review_request(
            response,
            language_mode=language_mode,
            learning_objective=learning_objective,
            learner_level=learner_level,
            correlation_id=correlation_id,
        )
        if language_mode == LanguageMode.ENGLISH:
            result = LanguageReviewResult(
                final_text=request.source_tutor_message,
                final_correction_explanation=request.source_correction_explanation,
                final_conversation_question=request.source_conversation_question,
                final_encouragement=request.source_encouragement,
                language_mode=language_mode,
                review_changed=False,
                review_reason_code=ReviewReasonCode.NOT_REQUIRED,
                preserved_learning_terms=request.required_learning_terms,
                expression_hint=ExpressionHint.NEUTRAL,
                source_content_digest=request.source_content_digest,
                provider_metadata_reference="language-review:pass-through:v1",
                usage=UsageInfo(provider_requests=0),
            )
        else:
            if self.provider is None:
                raise ProviderConfigurationError(
                    "Native Telugu review provider is not configured.",
                    provider_requests=0,
                    schema_path="provider",
                )
            result = self.provider.review(request)
        result = _normalize_result_output(result)
        _validate_result(request, result)
        if language_mode == LanguageMode.ENGLISH:
            return response, result
        reviewed = response.model_copy(update={
            "tutor_message": result.final_text,
            "correction_explanation": result.final_correction_explanation,
            "conversation_question": result.final_conversation_question,
            "encouragement": result.final_encouragement,
            "provider_metadata_reference": (
                f"{response.provider_metadata_reference}+{result.provider_metadata_reference}"
            )[:100],
            "usage": UsageInfo(
                input_units=response.usage.input_units + result.usage.input_units,
                cached_input_units=response.usage.cached_input_units + result.usage.cached_input_units,
                output_units=response.usage.output_units + result.usage.output_units,
                provider_requests=response.usage.provider_requests + result.usage.provider_requests,
            ),
        })
        if protected_content_digest(
            reviewed,
            learning_objective=learning_objective,
        ) != request.source_content_digest:
            raise ProviderOutputInvalid("Protected tutor content changed during review.", schema_path="protected_content")
        return reviewed, result


def degraded_review_result(
    response: AIConversationResponse,
    *,
    language_mode: LanguageMode,
    learning_objective: str,
    learner_level: str,
    correlation_id: str,
    failure_code: str,
) -> LanguageReviewResult:
    """Bind reviewer failure metadata to the unchanged validated response."""
    request = build_review_request(
        response,
        language_mode=language_mode,
        learning_objective=learning_objective,
        learner_level=learner_level,
        correlation_id=correlation_id,
    )
    return LanguageReviewResult(
        final_text=response.tutor_message,
        final_correction_explanation=response.correction_explanation,
        final_conversation_question=response.conversation_question,
        final_encouragement=response.encouragement,
        language_mode=language_mode,
        review_changed=False,
        review_reason_code=ReviewReasonCode.NOT_REQUIRED,
        preserved_learning_terms=request.required_learning_terms,
        expression_hint=ExpressionHint.NEUTRAL,
        source_content_digest=request.source_content_digest,
        status=LanguageReviewStatus.DEGRADED,
        failure_code=failure_code,
        provider_metadata_reference="language-review:degraded:canonical-v1",
        usage=UsageInfo(provider_requests=0),
    )

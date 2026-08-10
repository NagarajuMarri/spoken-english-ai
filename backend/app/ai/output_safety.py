from __future__ import annotations

from backend.app.ai.exceptions import ProviderOutputInvalid
from backend.app.ai.models import AIConversationResponse
from backend.app.domain.enums import LanguageMode
from backend.app.unicode_safety import UnicodeSafetyError, normalize_output_text


def _checked(
    value: str,
    *,
    path: str,
    allow_telugu: bool,
    require_lexical: bool = True,
) -> str:
    try:
        return normalize_output_text(
            value,
            allow_telugu=allow_telugu,
            require_lexical=require_lexical,
        )
    except UnicodeSafetyError as exc:
        raise ProviderOutputInvalid(
            "Learner-facing output failed Unicode or script validation.",
            schema_path=path,
        ) from exc


def enforce_response_output_safety(
    response: AIConversationResponse,
    language_mode: LanguageMode,
) -> AIConversationResponse:
    """Validate every learner-facing response field before checkpoint or persistence."""

    allow_telugu = language_mode != LanguageMode.ENGLISH
    scalar_fields = (
        "tutor_message",
        "corrected_learner_sentence",
        "correction_explanation",
        "conversation_question",
        "encouragement",
    )
    updates: dict[str, object] = {}
    for field in scalar_fields:
        value = getattr(response, field)
        if value is not None:
            updates[field] = _checked(
                value,
                path=field,
                allow_telugu=allow_telugu,
            )
    for field in ("grammar_feedback", "vocabulary_suggestions"):
        updates[field] = [
            _checked(item, path=f"{field}.{index}", allow_telugu=allow_telugu)
            for index, item in enumerate(getattr(response, field))
        ]
    learning_signals = response.learning_signals.model_copy(
        update={
            "grammar_focus": [
                _checked(
                    item,
                    path=f"learning_signals.grammar_focus.{index}",
                    allow_telugu=allow_telugu,
                )
                for index, item in enumerate(response.learning_signals.grammar_focus)
            ],
            "vocabulary": [
                _checked(
                    item,
                    path=f"learning_signals.vocabulary.{index}",
                    allow_telugu=allow_telugu,
                )
                for index, item in enumerate(response.learning_signals.vocabulary)
            ],
        }
    )
    updates["learning_signals"] = learning_signals
    return response.model_copy(update=updates)


def enforce_api_result_output_safety(result: dict, language_mode: LanguageMode) -> dict:
    """Protect derived coaching fields and replayed evidence before API/persistence/TTS."""

    safe = dict(result)
    allow_telugu = language_mode != LanguageMode.ENGLISH
    for field in (
        "tutor_message",
        "corrected_sentence",
        "correction_explanation",
        "next_question",
        "encouragement",
        "telugu_explanation",
        "spoken_text",
    ):
        value = safe.get(field)
        if isinstance(value, str):
            safe[field] = _checked(
                value,
                path=field,
                allow_telugu=allow_telugu,
            )
    for field in ("incorrect_span", "corrected_form"):
        value = safe.get(field)
        if isinstance(value, str):
            safe[field] = _checked(
                value,
                path=field,
                allow_telugu=True,
                require_lexical=False,
            )
    default_explanation = safe.get("correction_explanation_default")
    if isinstance(default_explanation, str):
        safe["correction_explanation_default"] = _checked(
            default_explanation,
            path="correction_explanation_default",
            allow_telugu=True,
        )
    for field in ("vocabulary_suggestions", "preserved_learning_terms"):
        values = safe.get(field)
        if isinstance(values, list):
            safe[field] = [
                _checked(item, path=f"{field}.{index}", allow_telugu=allow_telugu) if isinstance(item, str) else item
                for index, item in enumerate(values)
            ]
    return safe


def normalize_spoken_output(value: str, language_mode: LanguageMode) -> str:
    return _checked(
        value,
        path="spoken_text",
        allow_telugu=language_mode != LanguageMode.ENGLISH,
    )

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from enum import StrEnum

from backend.app.ai.models import AIConversationResponse
from backend.app.domain.enums import LanguageMode
from backend.app.explanation_language import ExplanationLanguageState


class CoachingMode(StrEnum):
    NO_CORRECTION = "NO_CORRECTION"
    LIGHT_CORRECTION = "LIGHT_CORRECTION"
    RETRY_REQUIRED = "RETRY_REQUIRED"


class CoachingState(StrEnum):
    NORMAL_CONVERSATION = "NORMAL_CONVERSATION"
    CORRECTION_PRESENTED = "CORRECTION_PRESENTED"
    WAITING_FOR_RETRY = "WAITING_FOR_RETRY"
    RETRY_ACCEPTED = "RETRY_ACCEPTED"
    CONTINUE_CONVERSATION = "CONTINUE_CONVERSATION"


@dataclass(frozen=True)
class CoachingOutcome:
    response: AIConversationResponse
    mode: CoachingMode
    state: CoachingState
    spoken_text: str
    incorrect_span: str | None = None
    corrected_form: str | None = None
    retry_of_turn_id: str | None = None


def _normalized(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.lower()))


def retry_matches(learner_text: str, corrected_sentence: str) -> bool:
    actual = _normalized(learner_text)
    expected = _normalized(corrected_sentence)
    if not actual or not expected:
        return False
    return actual == expected or SequenceMatcher(None, actual, expected).ratio() >= 0.86


def pending_retry(previous_result: dict | None) -> bool:
    return bool(previous_result and previous_result.get("coaching_state") == CoachingState.WAITING_FOR_RETRY)


def tutor_input_for_retry(message: str, previous_result: dict | None) -> str:
    if not pending_retry(previous_result):
        return message
    prior = previous_result or {}
    target = str(prior.get("corrected_sentence") or "")
    if retry_matches(message, target):
        return (
            f"The learner successfully retried the requested corrected sentence: {message}. "
            "Acknowledge the successful retry briefly, then continue the existing English-practice topic."
        )
    return (
        f"The learner is retrying a correction but has not yet matched the requested form: {message}. "
        "Do not introduce a new topic. Encourage one more retry."
    )


def correction_reexplanation_input(previous_result: dict | None, *, in_english: bool) -> str | None:
    if not pending_retry(previous_result):
        return None
    prior = previous_result or {}
    corrected = str(prior.get("corrected_sentence") or "").strip()
    if not corrected:
        return None
    language = "clear English" if in_english else "natural conversational Telugu"
    return (
        f'The learner explicitly asked to re-explain the pending correction in {language}. '
        f'The accepted corrected sentence is: "{corrected}". Re-explain the same correction evidence; '
        "do not introduce a new correction or topic, and ask the learner to retry that sentence."
    )


def _acknowledgement(mode: LanguageMode) -> str:
    if mode == LanguageMode.ENGLISH:
        return "I understood what you meant."
    return "మీ meaning clear గా ఉంది."


def _corrected_sentence(value: str, mode: LanguageMode) -> str:
    if mode == LanguageMode.ENGLISH:
        return f'A more natural sentence is: "{value}"'
    return f'Correct sentence: "{value}"'


def _retry_request(mode: LanguageMode, corrected_sentence: str | None = None, *, again: bool = False) -> str:
    target = f' "{corrected_sentence}"' if corrected_sentence else ""
    if mode == LanguageMode.ENGLISH:
        return f"Please say the corrected sentence once more:{target}" if again else f"Please say the corrected sentence once:{target}"
    return f"ఇప్పుడు corrected sentence ని ఇంకొకసారి చెప్పండి:{target}" if again else f"ఇప్పుడు corrected sentence ని ఒకసారి చెప్పండి:{target}"


def _retry_accepted(mode: LanguageMode) -> str:
    return "Good, that corrected sentence is right." if mode == LanguageMode.ENGLISH else "చాలా బాగా చెప్పారు. Corrected sentence ఇప్పుడు సరైంది."


def _join(*parts: str | None) -> str:
    return " ".join(part.strip() for part in parts if part and part.strip())


def _tokens(value: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9]+(?:'[A-Za-z]+)?|[^\w\s]", value)


def smallest_useful_error_span(learner_text: str, corrected_text: str) -> tuple[str, str]:
    """Return aligned, compact learner/corrected fragments with grammatical context."""
    source = [token for token in _tokens(learner_text) if token not in ".?!"]
    target = [token for token in _tokens(corrected_text) if token not in ".?!"]
    if not source or not target:
        return learner_text.strip(), corrected_text.strip()
    matcher = SequenceMatcher(None, [t.lower() for t in source], [t.lower() for t in target])
    changes = [op for op in matcher.get_opcodes() if op[0] != "equal"]
    if not changes:
        return learner_text.strip(), corrected_text.strip()
    s0, s1 = min(op[1] for op in changes), max(op[2] for op in changes)
    t0, t1 = min(op[3] for op in changes), max(op[4] for op in changes)
    # Include a little shared context. For short utterances, the whole sentence is clearer.
    if len(source) <= 5 and "didn't" not in [token.lower() for token in source]:
        return learner_text.strip().rstrip(".?!"), corrected_text.strip().rstrip(".?!")
    source_lower = [token.lower() for token in source]
    target_lower = [token.lower() for token in target]
    before = 1
    after = 2
    if s0 > 0 and source_lower[s0 - 1] in {"didn't", "did", "doesn't", "does"}:
        after = 0
    elif source_lower[s0:s1] and source_lower[s0] in {"have", "has"}:
        before = 2
    s0, s1 = max(0, s0 - before), min(len(source), s1 + after)
    t0, t1 = max(0, t0 - before), min(len(target), t1 + after)
    boundaries = {"because", "but", "although", "while", "so"}
    while s1 > s0 and source_lower[s1 - 1] in boundaries:
        s1 -= 1
    while t1 > t0 and target_lower[t1 - 1] in boundaries:
        t1 -= 1
    return " ".join(source[s0:s1]).strip(" ,.!?"), " ".join(target[t0:t1]).strip(" ,.!?")


def _incorrect_then_correct(incorrect: str, corrected: str, mode: LanguageMode) -> str:
    if not incorrect:
        return _corrected_sentence(corrected, mode)
    if mode == LanguageMode.ENGLISH:
        return f'You said: "{incorrect}". Correct form: "{corrected}".'
    return f'మీరు "{incorrect}" అన్నారు. Correct form: "{corrected}".'


def build_coaching_outcome(
    response: AIConversationResponse,
    *,
    learner_level: str,
    language_mode: LanguageMode,
    previous_result: dict | None = None,
    previous_turn_id: str | None = None,
    learner_text: str = "",
    explanation_language_state: ExplanationLanguageState = ExplanationLanguageState.DEFAULT_PREFERENCE,
) -> CoachingOutcome:
    if pending_retry(previous_result):
        prior = previous_result or {}
        target = str(prior.get("corrected_sentence") or "")
        if (
            explanation_language_state == ExplanationLanguageState.DEFAULT_PREFERENCE
            and retry_matches(learner_text, target)
        ):
            spoken = _join(_retry_accepted(language_mode), response.tutor_message, response.conversation_question)
            return CoachingOutcome(
                response=response,
                mode=CoachingMode.NO_CORRECTION,
                state=CoachingState.RETRY_ACCEPTED,
                spoken_text=spoken,
                retry_of_turn_id=previous_turn_id,
            )
        current_explanation = response.correction_explanation
        previous_explanation = str(
            prior.get("correction_explanation_default")
            or prior.get("correction_explanation")
            or ""
        ) or None
        explanation = (
            current_explanation
            if explanation_language_state != ExplanationLanguageState.DEFAULT_PREFERENCE and current_explanation
            else previous_explanation
        )
        linked = response.model_copy(update={
            "corrected_learner_sentence": target,
            "correction_explanation": explanation,
        })
        prior_incorrect = str(prior.get("incorrect_span") or learner_text).strip()
        prior_corrected_form = str(prior.get("corrected_form") or target).strip()
        if explanation_language_state == ExplanationLanguageState.DEFAULT_PREFERENCE:
            prior_incorrect, prior_corrected_form = smallest_useful_error_span(learner_text, target)
        spoken = _join(
            _incorrect_then_correct(prior_incorrect, prior_corrected_form, language_mode),
            explanation,
            _retry_request(language_mode, target, again=True),
        )
        return CoachingOutcome(
            response=linked,
            mode=CoachingMode.RETRY_REQUIRED,
            state=CoachingState.WAITING_FOR_RETRY,
            spoken_text=spoken,
            incorrect_span=prior_incorrect,
            corrected_form=prior_corrected_form,
            retry_of_turn_id=previous_turn_id,
        )

    corrected = response.corrected_learner_sentence
    explanation = response.correction_explanation
    if not corrected or not explanation:
        return CoachingOutcome(
            response=response,
            mode=CoachingMode.NO_CORRECTION,
            state=CoachingState.NORMAL_CONVERSATION,
            spoken_text=_join(response.tutor_message, response.conversation_question),
        )

    meaningful = learner_level.upper() in {"BEGINNER", "ELEMENTARY", "A1", "A2"} or len(response.grammar_feedback) > 1
    incorrect_span, corrected_form = smallest_useful_error_span(learner_text, corrected)
    if meaningful:
        spoken = _join(
            _incorrect_then_correct(incorrect_span, corrected_form, language_mode),
            explanation,
            _retry_request(language_mode, corrected),
        )
        return CoachingOutcome(
            response=response,
            mode=CoachingMode.RETRY_REQUIRED,
            state=CoachingState.WAITING_FOR_RETRY,
            spoken_text=spoken,
            incorrect_span=incorrect_span,
            corrected_form=corrected_form,
        )

    return CoachingOutcome(
        response=response,
        mode=CoachingMode.LIGHT_CORRECTION,
        state=CoachingState.CORRECTION_PRESENTED,
        spoken_text=_join(
            _incorrect_then_correct(incorrect_span, corrected_form, language_mode),
            explanation,
            response.tutor_message,
            response.conversation_question,
        ),
        incorrect_span=incorrect_span,
        corrected_form=corrected_form,
    )

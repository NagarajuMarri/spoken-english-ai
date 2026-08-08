from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from enum import StrEnum

from backend.app.ai.models import AIConversationResponse
from backend.app.domain.enums import LanguageMode


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


def _acknowledgement(mode: LanguageMode) -> str:
    if mode == LanguageMode.ENGLISH:
        return "I understood what you meant."
    return "మీ meaning clear గా ఉంది."


def _corrected_sentence(value: str, mode: LanguageMode) -> str:
    if mode == LanguageMode.ENGLISH:
        return f'A more natural sentence is: "{value}"'
    return f'Correct sentence: "{value}"'


def _retry_request(mode: LanguageMode, *, again: bool = False) -> str:
    if mode == LanguageMode.ENGLISH:
        return "Please say the corrected sentence once more." if again else "Please say the corrected sentence once."
    return "ఇప్పుడు corrected sentence ని ఇంకొకసారి చెప్పండి." if again else "ఇప్పుడు corrected sentence ని ఒకసారి చెప్పండి."


def _retry_accepted(mode: LanguageMode) -> str:
    return "Good, that corrected sentence is right." if mode == LanguageMode.ENGLISH else "చాలా బాగా చెప్పారు. Corrected sentence ఇప్పుడు సరైంది."


def _join(*parts: str | None) -> str:
    return " ".join(part.strip() for part in parts if part and part.strip())


def build_coaching_outcome(
    response: AIConversationResponse,
    *,
    learner_level: str,
    language_mode: LanguageMode,
    previous_result: dict | None = None,
    previous_turn_id: str | None = None,
    learner_text: str = "",
) -> CoachingOutcome:
    if pending_retry(previous_result):
        prior = previous_result or {}
        target = str(prior.get("corrected_sentence") or "")
        if retry_matches(learner_text, target):
            spoken = _join(_retry_accepted(language_mode), response.tutor_message, response.conversation_question)
            return CoachingOutcome(
                response=response,
                mode=CoachingMode.NO_CORRECTION,
                state=CoachingState.RETRY_ACCEPTED,
                spoken_text=spoken,
                retry_of_turn_id=previous_turn_id,
            )
        previous_explanation = str(prior.get("correction_explanation") or "") or None
        linked = response.model_copy(update={
            "corrected_learner_sentence": target,
            "correction_explanation": previous_explanation,
        })
        spoken = _join(
            _acknowledgement(language_mode),
            _corrected_sentence(target, language_mode),
            previous_explanation,
            _retry_request(language_mode, again=True),
        )
        return CoachingOutcome(
            response=linked,
            mode=CoachingMode.RETRY_REQUIRED,
            state=CoachingState.WAITING_FOR_RETRY,
            spoken_text=spoken,
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
    if meaningful:
        spoken = _join(
            _acknowledgement(language_mode),
            _corrected_sentence(corrected, language_mode),
            explanation,
            _retry_request(language_mode),
        )
        return CoachingOutcome(
            response=response,
            mode=CoachingMode.RETRY_REQUIRED,
            state=CoachingState.WAITING_FOR_RETRY,
            spoken_text=spoken,
        )

    return CoachingOutcome(
        response=response,
        mode=CoachingMode.LIGHT_CORRECTION,
        state=CoachingState.CORRECTION_PRESENTED,
        spoken_text=_join(
            _acknowledgement(language_mode),
            _corrected_sentence(corrected, language_mode),
            explanation,
            response.tutor_message,
            response.conversation_question,
        ),
    )

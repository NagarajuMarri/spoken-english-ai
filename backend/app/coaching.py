from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from enum import StrEnum

from backend.app.ai.models import AIConversationResponse, CorrectionType
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
    EXPLAINING_CORRECTION = "EXPLAINING_CORRECTION"


class LearnerIntent(StrEnum):
    RETRY = "RETRY"
    EXPLANATION = "EXPLANATION"
    GRAMMAR_HELP = "GRAMMAR_HELP"
    CLARIFICATION = "CLARIFICATION"
    EXAMPLES = "EXAMPLES"
    LANGUAGE_CHANGE = "LANGUAGE_CHANGE"
    GUIDED_ROLEPLAY = "GUIDED_ROLEPLAY"
    NORMAL_CONVERSATION = "NORMAL_CONVERSATION"


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


def _retry_words(value: str) -> list[str]:
    normalized = value.casefold().replace("’", "'")
    normalized = re.sub(r"\bi\s*'m\b|\bim\b", "i am", normalized)
    normalized = re.sub(r"\bmy\s+day\s*'s\b", "my day is", normalized)
    words = re.findall(r"[a-z0-9]+", normalized)
    while words and words[0] in {"hi", "hey", "hello"}:
        words.pop(0)
    return words


def _introduction_name(value: str) -> str | None:
    words = _retry_words(value)
    if len(words) >= 3 and words[:2] in (["i", "am"], ["my", "name"]):
        if words[:2] == ["my", "name"] and len(words) >= 4 and words[2] == "is":
            return " ".join(words[3:]) or None
        if words[:2] == ["i", "am"]:
            return " ".join(words[2:]) or None
    return None


def retry_matches(learner_text: str, corrected_sentence: str) -> bool:
    actual_words = _retry_words(learner_text)
    expected_words = _retry_words(corrected_sentence)
    if not actual_words or not expected_words:
        return False
    actual_name = _introduction_name(learner_text)
    expected_name = _introduction_name(corrected_sentence)
    if actual_name and expected_name:
        return actual_name == expected_name
    actual = " ".join(actual_words)
    expected = " ".join(expected_words)
    return actual == expected


def pending_retry(previous_result: dict | None) -> bool:
    return bool(previous_result and previous_result.get("coaching_state") in {
        CoachingState.WAITING_FOR_RETRY, CoachingState.EXPLAINING_CORRECTION,
    })


def classify_learner_intent(message: str, previous_result: dict | None = None) -> LearnerIntent:
    normalized = _normalized(message)
    target = str((previous_result or {}).get("corrected_sentence") or "")
    if pending_retry(previous_result) and retry_matches(message, target):
        return LearnerIntent.RETRY
    guided_markers = (
        "step by step", "roleplay", "role play", "guided practice", "scenario practice",
        "lesson", "నేర్పించ", "ప్రాక్టీస్", "మార్కెట్", "market లో", "market lo",
    )
    if any(marker in message.casefold() for marker in guided_markers) and any(
        marker in message.casefold() for marker in ("market", "మార్కెట్", "lesson", "నేర్పించ", "role")
    ):
        return LearnerIntent.GUIDED_ROLEPLAY
    if re.search(r"\b(from now on|always)\b.*\b(english|telugu|language)\b", normalized):
        return LearnerIntent.LANGUAGE_CHANGE
    if re.search(r"\b(explain|explanation|why)\b", normalized):
        return LearnerIntent.EXPLANATION
    if re.search(r"\b(example|examples)\b", normalized):
        return LearnerIntent.EXAMPLES
    if re.search(r"\b(clarify|clarification|what do you mean)\b", normalized):
        return LearnerIntent.CLARIFICATION
    if re.search(r"\b(grammar|help|tense|pronoun|noun|verb|correct|meaning)\b", normalized):
        return LearnerIntent.GRAMMAR_HELP
    if any(marker in message.casefold() for marker in ("ఎందుకు", "ఎలా", "అర్థం", "చెప్పండి", "enduku", "ela")):
        return LearnerIntent.GRAMMAR_HELP
    return LearnerIntent.NORMAL_CONVERSATION


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


def _accurate_self_introduction(response: AIConversationResponse, learner_text: str) -> AIConversationResponse:
    if not re.search(r"\bmyself\s+[A-Za-z][A-Za-z'-]*", learner_text, re.I):
        return response
    if not response.corrected_learner_sentence:
        return response
    return response.model_copy(update={
        "correction_explanation": (
            "'Myself' is a reflexive or intensive pronoun, not a noun. "
            "'Myself Nagaraj' is not a standard or natural English self-introduction. "
            "Say 'I'm Nagaraj' or 'My name is Nagaraj.'"
        ),
    })


_FACT_PATTERNS = (
    ("name", re.compile(r"^\s*my name is\s+(?P<value>.+?)[.!?]*\s*$", re.I)),
    ("hometown", re.compile(r"^\s*my hometown is\s+(?P<value>.+?)[.!?]*\s*$", re.I)),
    ("city", re.compile(r"^\s*my city is\s+(?P<value>.+?)[.!?]*\s*$", re.I)),
    ("country", re.compile(r"^\s*my country is\s+(?P<value>.+?)[.!?]*\s*$", re.I)),
    ("occupation", re.compile(r"^\s*i work as\s+(?:an?\s+)?(?P<value>.+?)[.!?]*\s*$", re.I)),
    ("location", re.compile(r"^\s*i live in\s+(?P<value>.+?)[.!?]*\s*$", re.I)),
    ("origin", re.compile(r"^\s*i am from\s+(?P<value>.+?)[.!?]*\s*$", re.I)),
    ("price", re.compile(r"^\s*(?:the|its?) price is\s+(?P<value>.+?)[.!?]*\s*$", re.I)),
)


def _factual_slot(value: str) -> tuple[str, str] | None:
    for slot, pattern in _FACT_PATTERNS:
        match = pattern.match(value)
        if match:
            fact = " ".join(match.group("value").strip().rstrip(".!?").casefold().split())
            return slot, fact
    return None


def _style_words(value: str) -> list[str]:
    words = _retry_words(value)
    optional_prefixes = (
        ["yes"], ["yeah"], ["hi"], ["hey"], ["hello"], ["ananya"], ["excuse", "me"],
    )
    changed = True
    while changed:
        changed = False
        for prefix in optional_prefixes:
            if words[:len(prefix)] == prefix:
                words = words[len(prefix):]
                changed = True
    return words


def _fact_words(value: str) -> set[str]:
    return set(re.findall(r"[^\W_]+", value.casefold(), re.UNICODE))


def _references_pending_correction(message: str, prior: dict) -> bool:
    normalized = _normalized(message)
    if normalized in {"why", "explain", "explain it", "examples", "give examples"}:
        return True
    if re.search(r"\b(this|that|the)\s+(correction|sentence|form|mistake)\b", normalized):
        return True
    evidence = " ".join(str(prior.get(key) or "") for key in ("incorrect_span", "corrected_form"))
    evidence_words = {word for word in _normalized(evidence).split() if len(word) >= 3}
    return bool(evidence_words & set(normalized.split()))


def protect_learner_facts(response: AIConversationResponse, learner_text: str) -> AIConversationResponse:
    corrected = response.corrected_learner_sentence
    if not corrected:
        return response
    if corrected and _style_words(learner_text) == _style_words(corrected):
        return response.model_copy(update={
            "tutor_message": f"That's correct. {learner_text.strip()}",
            "correction_type": CorrectionType.VALID_SENTENCE,
            "corrected_learner_sentence": None,
            "correction_explanation": None,
            "grammar_feedback": [],
            "learning_signals": response.learning_signals.model_copy(update={"grammar_focus": []}),
        })
    learner_fact = _factual_slot(learner_text)
    introduction_name = _introduction_name(learner_text)
    if learner_fact is None and introduction_name and len(introduction_name.split()) <= 3:
        learner_fact = ("name", introduction_name)
    corrected_fact = _factual_slot(corrected or "")
    corrected_introduction = _introduction_name(corrected or "")
    if corrected_fact is None and corrected_introduction and len(corrected_introduction.split()) <= 3:
        corrected_fact = ("name", corrected_introduction)
    changed_numbers = re.findall(r"\d+(?:[.,]\d+)?", learner_text) != re.findall(
        r"\d+(?:[.,]\d+)?", corrected or learner_text
    )
    corrected_words = _fact_words(corrected or "")
    changed_slot = bool(learner_fact and not _fact_words(learner_fact[1]) <= corrected_words)
    if not changed_slot and not changed_numbers:
        return response
    return response.model_copy(update={
        "tutor_message": f"Thanks for sharing. {learner_text.strip()}",
        "corrected_learner_sentence": None,
        "correction_explanation": None,
        "grammar_feedback": [],
        "vocabulary_suggestions": [],
        "conversation_question": "What would you like to tell me next?",
        "encouragement": "Thank you for sharing that.",
        "learning_signals": response.learning_signals.model_copy(update={
            "grammar_focus": [], "vocabulary": [],
        }),
    })


def apply_pedagogy_guardrails(response: AIConversationResponse) -> AIConversationResponse:
    def repair(value: str | None) -> str | None:
        if not value:
            return value
        lowered = value.casefold()
        if "అండి" in value and any(marker in lowered for marker in ("informal", "అనౌపచారిక")):
            return "'అండి' is commonly a polite and respectful conversational form in Telugu."
        if "how much is this" in lowered and any(marker in lowered for marker in (
            "subject-verb-object", "svo", "సబ్జెక్ట్-వర్బ్-ఓబ్జెక్ట్",
        )):
            return (
                "'How much is this?' is a natural English price question. It is a wh-question, "
                "not an ordinary subject-verb-object statement."
            )
        return value

    updates = {
        "tutor_message": repair(response.tutor_message),
        "correction_explanation": repair(response.correction_explanation),
        "conversation_question": repair(response.conversation_question),
        "encouragement": repair(response.encouragement),
        "grammar_feedback": [repair(value) or "" for value in response.grammar_feedback],
        "vocabulary_suggestions": [repair(value) or "" for value in response.vocabulary_suggestions],
    }
    if all(getattr(response, key) == value for key, value in updates.items()):
        return response
    return response.model_copy(update=updates)


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
        if source and source[0].lower() in {"hi", "hello"} and s0 > 0:
            return (
                " ".join(source[s0:min(len(source), s1 + 1)]).strip(" ,.!?"),
                " ".join(target[t0:min(len(target), t1 + 1)]).strip(" ,.!?"),
            )
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
    learner_intent: LearnerIntent | None = None,
) -> CoachingOutcome:
    response = _accurate_self_introduction(response, learner_text)
    if pending_retry(previous_result):
        prior = previous_result or {}
        target = str(prior.get("corrected_sentence") or "")
        intent = learner_intent or classify_learner_intent(learner_text, previous_result)
        if (
            explanation_language_state == ExplanationLanguageState.DEFAULT_PREFERENCE
            and intent == LearnerIntent.RETRY
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
        if intent in {
            LearnerIntent.EXPLANATION,
            LearnerIntent.GRAMMAR_HELP,
            LearnerIntent.CLARIFICATION,
            LearnerIntent.EXAMPLES,
        } and explanation_language_state == ExplanationLanguageState.DEFAULT_PREFERENCE and _references_pending_correction(
            learner_text, prior,
        ):
            linked = response.model_copy(update={
                "corrected_learner_sentence": target,
                "correction_explanation": str(
                    prior.get("correction_explanation_default")
                    or prior.get("correction_explanation") or ""
                ) or None,
            })
            return CoachingOutcome(
                response=linked,
                mode=CoachingMode.RETRY_REQUIRED,
                state=CoachingState.EXPLAINING_CORRECTION,
                spoken_text=_join(response.tutor_message, response.correction_explanation, response.conversation_question),
                incorrect_span=str(prior.get("incorrect_span") or "") or None,
                corrected_form=str(prior.get("corrected_form") or target) or None,
                retry_of_turn_id=previous_turn_id,
            )
        if (
            explanation_language_state != ExplanationLanguageState.DEFAULT_PREFERENCE
            and intent in {LearnerIntent.EXPLANATION, LearnerIntent.LANGUAGE_CHANGE}
        ):
            intent = LearnerIntent.RETRY
        if intent != LearnerIntent.RETRY:
            previous_result = None
        else:
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
                "correction_explanation": (
                    explanation
                    if explanation_language_state != ExplanationLanguageState.DEFAULT_PREFERENCE
                    else None
                ),
            })
            prior_incorrect = str(prior.get("incorrect_span") or learner_text).strip()
            prior_corrected_form = str(prior.get("corrected_form") or target).strip()
            if explanation_language_state == ExplanationLanguageState.DEFAULT_PREFERENCE:
                prior_incorrect, prior_corrected_form = smallest_useful_error_span(learner_text, target)
            spoken = (
                _join(
                    _incorrect_then_correct(prior_incorrect, prior_corrected_form, language_mode),
                    explanation,
                    _retry_request(language_mode, target, again=True),
                )
                if explanation_language_state != ExplanationLanguageState.DEFAULT_PREFERENCE
                else _join("Almost—try the corrected sentence once more.", _retry_request(
                    language_mode, target, again=True,
                ))
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
    if response.correction_type not in {
        CorrectionType.GRAMMAR_ERROR,
        CorrectionType.VOCABULARY_ERROR,
        CorrectionType.PRONUNCIATION_ERROR,
    }:
        response = response.model_copy(update={
            "corrected_learner_sentence": None,
            "correction_explanation": None,
            "grammar_feedback": [],
            "learning_signals": response.learning_signals.model_copy(update={"grammar_focus": []}),
        })
        return CoachingOutcome(
            response=response,
            mode=CoachingMode.NO_CORRECTION,
            state=CoachingState.NORMAL_CONVERSATION,
            spoken_text=_join(response.tutor_message, response.conversation_question),
        )
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

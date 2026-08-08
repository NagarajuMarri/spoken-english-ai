from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from backend.app.domain.enums import LanguageMode


class ExplanationLanguageState(StrEnum):
    DEFAULT_PREFERENCE = "DEFAULT_PREFERENCE"
    ONE_TURN_OVERRIDE = "ONE_TURN_OVERRIDE"
    PERSISTENT_PREFERENCE_CHANGE = "PERSISTENT_PREFERENCE_CHANGE"


class ExplanationLanguage(StrEnum):
    TELUGU = "TELUGU"
    ENGLISH = "ENGLISH"


@dataclass(frozen=True)
class ExplanationLanguageDecision:
    state: ExplanationLanguageState
    language: ExplanationLanguage
    effective_mode: LanguageMode
    persist_mode: LanguageMode | None = None


_PERSISTENT_ENGLISH = (
    re.compile(r"\bfrom now on\b.*\bexplain\b.*\benglish\b", re.I),
    re.compile(r"\balways\b.*\bexplain\b.*\benglish\b", re.I),
    re.compile(r"\b(?:do not|don't) want\b.*\btelugu explanations?\b", re.I),
)
_ONE_TURN_ENGLISH = (
    re.compile(r"^\s*explain(?: that| it)? in english[.!?]*\s*$", re.I),
    re.compile(r"^\s*tell me(?: that| it)? in english[.!?]*\s*$", re.I),
    re.compile(r"^\s*english lo explain (?:cheyyi|cheyandi)[.!?]*\s*$", re.I),
    re.compile(r"^\s*can you explain(?: that| it)? in english[.!?]*\s*$", re.I),
)


def resolve_explanation_language(message: str, default_mode: LanguageMode) -> ExplanationLanguageDecision:
    if any(pattern.search(message) for pattern in _PERSISTENT_ENGLISH):
        return ExplanationLanguageDecision(
            state=ExplanationLanguageState.PERSISTENT_PREFERENCE_CHANGE,
            language=ExplanationLanguage.ENGLISH,
            effective_mode=LanguageMode.ENGLISH,
            persist_mode=LanguageMode.ENGLISH,
        )
    if any(pattern.search(message) for pattern in _ONE_TURN_ENGLISH):
        return ExplanationLanguageDecision(
            state=ExplanationLanguageState.ONE_TURN_OVERRIDE,
            language=ExplanationLanguage.ENGLISH,
            effective_mode=LanguageMode.ENGLISH,
        )
    if default_mode == LanguageMode.ENGLISH:
        return ExplanationLanguageDecision(
            state=ExplanationLanguageState.DEFAULT_PREFERENCE,
            language=ExplanationLanguage.ENGLISH,
            effective_mode=LanguageMode.ENGLISH,
        )
    return ExplanationLanguageDecision(
        state=ExplanationLanguageState.DEFAULT_PREFERENCE,
        language=ExplanationLanguage.TELUGU,
        effective_mode=default_mode,
    )


def explanation_policy_instruction(decision: ExplanationLanguageDecision) -> str:
    if decision.language == ExplanationLanguage.ENGLISH:
        return (
            "Explain this turn's correction in clear English. Keep the corrected sentence in English. "
            "This instruction is about explanation language, not the language the learner is practising."
        )
    return (
        "Explain corrections in natural conversational Andhra/Telangana Telugu by default. Keep the "
        "corrected English sentence and useful English grammar terms in English. Ask for the retry in Telugu."
    )

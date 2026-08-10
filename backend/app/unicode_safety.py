from __future__ import annotations

import unicodedata
from typing import Literal


class UnicodeSafetyError(ValueError):
    """Privacy-safe failure raised for malformed or unsupported learner-facing text."""


_TELUGU_START, _TELUGU_END = 0x0C00, 0x0C7F
_TELUGU_VOWEL_SIGNS = (
    set(range(0x0C3E, 0x0C45))
    | set(range(0x0C46, 0x0C49))
    | set(range(0x0C4A, 0x0C4D))
    | {0x0C55, 0x0C56, 0x0C62, 0x0C63}
)
_TELUGU_VIRAMA = 0x0C4D
_JOINERS = {"\u200c", "\u200d"}
# Inherited marks that are useful for Latin/Telugu learner text. Script-specific
# marks outside the Telugu block must not become implicitly trusted merely
# because Python reports their Unicode script as Inherited/Common.
_SUPPORTED_INHERITED_MARK_RANGES = (
    (0x0300, 0x036F),  # Combining Diacritical Marks
    (0x1AB0, 0x1AFF),  # Combining Diacritical Marks Extended
    (0x1DC0, 0x1DFF),  # Combining Diacritical Marks Supplement
    (0xFE20, 0xFE2F),  # Combining Half Marks
)
_BIDI_CONTROL_CODEPOINTS = {
    *range(0x202A, 0x202F),
    *range(0x2066, 0x206A),
    0x061C,
    0x200E,
    0x200F,
}
_SCRIPTED_MARK_NAMES = {
    "ARABIC",
    "BENGALI",
    "CYRILLIC",
    "DEVANAGARI",
    "GUJARATI",
    "GURMUKHI",
    "HEBREW",
    "KANNADA",
    "MALAYALAM",
    "ORIYA",
    "SINHALA",
    "TAMIL",
    "THAI",
}


def _is_noncharacter(codepoint: int) -> bool:
    return 0xFDD0 <= codepoint <= 0xFDEF or (codepoint & 0xFFFF) in {0xFFFE, 0xFFFF}


def _is_supported_inherited_mark(codepoint: int) -> bool:
    return any(start <= codepoint <= end for start, end in _SUPPORTED_INHERITED_MARK_RANGES)


def _script(character: str) -> str:
    codepoint = ord(character)
    if _TELUGU_START <= codepoint <= _TELUGU_END:
        return "telugu"
    name = unicodedata.name(character, "")
    if "LATIN" in name:
        return "latin"
    if any(script in name for script in _SCRIPTED_MARK_NAMES):
        return "unsupported"
    category = unicodedata.category(character)
    if category.startswith("M"):
        return "inherited"
    if category.startswith("L"):
        return "unsupported"
    return "common"


def _valid_joiner(text: str, index: int) -> bool:
    if index == 0 or index == len(text) - 1:
        return False
    previous = text[index - 1]
    following = text[index + 1]
    previous_script = _script(previous)
    following_script = _script(following)
    if previous_script == following_script == "telugu":
        return True
    while unicodedata.category(previous).startswith("M") and index > 1:
        index -= 1
        previous = text[index - 1]
    return unicodedata.category(previous).startswith("S") and unicodedata.category(following).startswith("S")


def normalize_supported_text(
    value: str,
    *,
    allow_telugu: bool,
    unsupported_policy: Literal["any", "substantive"],
    require_lexical: bool,
) -> str:
    """Normalize text and enforce the product's Latin/Telugu/Common/Inherited policy."""

    normalized = unicodedata.normalize("NFC", value).strip()
    if not normalized:
        raise UnicodeSafetyError("Text is empty.")

    allowed_scripts = {"latin", "common", "inherited"}
    if allow_telugu:
        allowed_scripts.add("telugu")

    lexical_count = 0
    unsupported_lexical_count = 0
    base_count = 0
    mark_count = 0
    combining_run = 0
    cluster_script: str | None = None
    telugu_vowel_seen = False
    telugu_virama_seen = False

    for index, character in enumerate(normalized):
        codepoint = ord(character)
        category = unicodedata.category(character)
        if _is_noncharacter(codepoint) or category == "Cs":
            raise UnicodeSafetyError("Text contains a prohibited Unicode code point.")
        if codepoint in _BIDI_CONTROL_CODEPOINTS:
            raise UnicodeSafetyError("Text contains a prohibited bidirectional control.")
        if character in _JOINERS:
            if not _valid_joiner(normalized, index):
                raise UnicodeSafetyError("Text contains a misplaced joiner.")
            continue
        if category.startswith("C"):
            if character not in {"\n", "\t"}:
                raise UnicodeSafetyError("Text contains a prohibited control character.")
            combining_run = 0
            cluster_script = None
            telugu_vowel_seen = False
            telugu_virama_seen = False
            continue

        script = _script(character)
        if category.startswith(("L", "N")):
            lexical_count += 1
            base_count += 1
            cluster_script = script
            if script not in allowed_scripts:
                unsupported_lexical_count += 1
            combining_run = 0
            telugu_vowel_seen = False
            telugu_virama_seen = False
        elif category.startswith("M"):
            mark_count += 1
            combining_run += 1
            if script not in allowed_scripts:
                raise UnicodeSafetyError("Text contains a mark from an unsupported script.")
            if script == "inherited" and (
                not _is_supported_inherited_mark(codepoint)
                or cluster_script not in {"latin", "telugu"}
            ):
                raise UnicodeSafetyError("Text contains a mark from an unsupported script or base.")
            if (
                index == 0
                or normalized[index - 1].isspace()
                or combining_run > 3
                or (script == "telugu" and cluster_script != "telugu")
            ):
                raise UnicodeSafetyError("Text contains malformed combining marks.")
            if script == "telugu" and codepoint == _TELUGU_VIRAMA:
                if telugu_vowel_seen:
                    raise UnicodeSafetyError("Text contains a malformed Telugu grapheme.")
                telugu_virama_seen = True
            elif script == "telugu" and codepoint in _TELUGU_VOWEL_SIGNS:
                if telugu_vowel_seen or telugu_virama_seen:
                    raise UnicodeSafetyError("Text contains a malformed Telugu grapheme.")
                telugu_vowel_seen = True
        else:
            combining_run = 0
            cluster_script = None
            telugu_vowel_seen = False
            telugu_virama_seen = False

    if require_lexical and lexical_count == 0:
        raise UnicodeSafetyError("Text has no lexical content.")
    if mark_count and base_count / (base_count + mark_count) < 0.2:
        raise UnicodeSafetyError("Text has too little lexical content.")
    if unsupported_lexical_count:
        unsupported_is_substantive = unsupported_lexical_count >= 2 or (
            unsupported_lexical_count / max(1, lexical_count) >= 0.5
        )
        if unsupported_policy == "any" or unsupported_is_substantive:
            raise UnicodeSafetyError("Text contains an unsupported writing system.")
    return normalized


def normalize_input_text(value: str) -> str:
    return normalize_supported_text(
        value,
        allow_telugu=True,
        unsupported_policy="substantive",
        require_lexical=True,
    )


def normalize_output_text(
    value: str,
    *,
    allow_telugu: bool = True,
    require_lexical: bool = True,
) -> str:
    return normalize_supported_text(
        value,
        allow_telugu=allow_telugu,
        unsupported_policy="any",
        require_lexical=require_lexical,
    )

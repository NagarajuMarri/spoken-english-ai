from __future__ import annotations

import unicodedata


class UnusableTranscript(ValueError):
    """Raised when a transcript is unsafe to show or persist."""


_TELUGU_START, _TELUGU_END = 0x0C00, 0x0C7F
_KANNADA_START, _KANNADA_END = 0x0C80, 0x0CFF
_TELUGU_VOWEL_SIGNS = set(range(0x0C3E, 0x0C45)) | set(range(0x0C46, 0x0C49)) | set(range(0x0C4A, 0x0C4D)) | {0x0C55, 0x0C56}
_TELUGU_VIRAMA = 0x0C4D


def _script(character: str) -> str | None:
    codepoint = ord(character)
    if _TELUGU_START <= codepoint <= _TELUGU_END:
        return "telugu"
    if _KANNADA_START <= codepoint <= _KANNADA_END:
        return "kannada"
    return None


def safe_transcript(value: str, *, expected_language: str | None = None) -> str:
    normalized = unicodedata.normalize("NFC", value).strip()
    if not normalized or not any(character.isalnum() for character in normalized):
        raise UnusableTranscript("Transcript has no lexical content.")
    combining_run = 0
    previous = ""
    cluster_script: str | None = None
    base_count = 0
    mark_count = 0
    telugu_bases = 0
    kannada_bases = 0
    telugu_vowel_seen = False
    telugu_virama_seen = False
    for character in normalized:
        category = unicodedata.category(character)
        script = _script(character)
        if category.startswith(("L", "N")):
            base_count += 1
            cluster_script = script
            if script == "telugu":
                telugu_bases += 1
            elif script == "kannada":
                kannada_bases += 1
            combining_run = 0
            telugu_vowel_seen = False
            telugu_virama_seen = False
        elif category.startswith("M"):
            mark_count += 1
            combining_run += 1
            if (
                not previous
                or previous.isspace()
                or combining_run > 3
                or (script is not None and cluster_script != script)
            ):
                raise UnusableTranscript("Transcript contains malformed combining marks.")
            codepoint = ord(character)
            if script == "telugu" and codepoint == _TELUGU_VIRAMA:
                if telugu_vowel_seen:
                    raise UnusableTranscript("Transcript contains a malformed Telugu grapheme.")
                telugu_virama_seen = True
            elif script == "telugu" and codepoint in _TELUGU_VOWEL_SIGNS:
                if telugu_vowel_seen or telugu_virama_seen:
                    raise UnusableTranscript("Transcript contains a malformed Telugu grapheme.")
                telugu_vowel_seen = True
        else:
            combining_run = 0
            if character not in {"\u200c", "\u200d"}:
                cluster_script = None
                telugu_vowel_seen = False
                telugu_virama_seen = False
        previous = character
    if mark_count and base_count / (base_count + mark_count) < 0.2:
        raise UnusableTranscript("Transcript has too little lexical content.")
    expected = (expected_language or "").casefold()
    indic_bases = telugu_bases + kannada_bases
    if (
        expected in {"te", "tel", "telugu"}
        and kannada_bases >= 2
        and indic_bases
        and kannada_bases / indic_bases >= 0.6
    ):
        raise UnusableTranscript("Transcript script does not match expected Telugu input.")
    return normalized

from __future__ import annotations

import unicodedata


class UnusableTranscript(ValueError):
    """Raised when a transcript is unsafe to show or persist."""


def safe_transcript(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value).strip()
    if not normalized or not any(character.isalnum() for character in normalized):
        raise UnusableTranscript("Transcript has no lexical content.")
    combining_run = 0
    previous = ""
    for character in normalized:
        if unicodedata.category(character).startswith("M"):
            combining_run += 1
            if not previous or previous.isspace() or combining_run > 3:
                raise UnusableTranscript("Transcript contains malformed combining marks.")
        else:
            combining_run = 0
        previous = character
    return normalized

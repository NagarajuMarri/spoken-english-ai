from __future__ import annotations

import re

from backend.app.unicode_safety import UnicodeSafetyError, normalize_input_text


class UnusableTranscript(ValueError):
    """Raised when a transcript is unsafe to show or persist."""


_ANANYA_GREETING_VARIANT = re.compile(
    r"^(?P<greeting>\s*(?:yeah[, ]+)?(?:hi|hey|hello)[, ]+)(?:an india(?: water)?|ananya)(?P<rest>\b.*)$",
    re.IGNORECASE,
)


def normalize_known_tutor_reference(value: str, *, confidence: float | None) -> str:
    """Normalize only controlled tutor-name variants in an explicit greeting context."""
    if confidence is not None and confidence < 0.55:
        return value
    match = _ANANYA_GREETING_VARIANT.match(value)
    if match is None:
        return value
    return f"{match.group('greeting')}Ananya{match.group('rest')}"


def safe_transcript(value: str, *, expected_language: str | None = None) -> str:
    # The supported-script boundary is product-wide; expected_language remains
    # part of the public contract so callers need not special-case it.
    _ = expected_language
    try:
        return normalize_input_text(value)
    except UnicodeSafetyError as exc:
        raise UnusableTranscript(str(exc)) from exc

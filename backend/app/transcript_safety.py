from __future__ import annotations

from backend.app.unicode_safety import UnicodeSafetyError, normalize_input_text


class UnusableTranscript(ValueError):
    """Raised when a transcript is unsafe to show or persist."""


def safe_transcript(value: str, *, expected_language: str | None = None) -> str:
    # The supported-script boundary is product-wide; expected_language remains
    # part of the public contract so callers need not special-case it.
    _ = expected_language
    try:
        return normalize_input_text(value)
    except UnicodeSafetyError as exc:
        raise UnusableTranscript(str(exc)) from exc

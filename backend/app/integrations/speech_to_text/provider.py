from typing import Protocol


class SpeechToTextProvider(Protocol):
    def transcribe(self, audio: bytes) -> str: ...


class FakeSpeechToTextProvider:
    def __init__(self, transcript: str = "Local test transcript.") -> None:
        self.transcript = transcript

    def transcribe(self, audio: bytes) -> str:
        return self.transcript

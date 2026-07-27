from typing import Protocol


class TextToSpeechProvider(Protocol):
    def synthesize(self, text: str) -> bytes: ...


class FakeTextToSpeechProvider:
    def synthesize(self, text: str) -> bytes:
        return f"FAKE_AUDIO:{text}".encode()

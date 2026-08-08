import hashlib
from backend.app.providers.tts.contracts import TextToSpeechResult


class DeterministicTextToSpeechProvider:
    name = "deterministic-tts"
    voices = {"supportive-neutral", "supportive-slow", "marin", "cedar"}

    def __init__(self):
        self.calls = 0

    def synthesize(self, request):
        if request.voice_reference not in self.voices:
            raise ValueError("Unsupported voice.")
        self.calls += 1
        digest = hashlib.sha256(request.text.encode()).hexdigest()[:16]
        # Valid RIFF/WAVE header with a tiny silent PCM payload for browser-safe tests.
        pcm = b"\x00\x00" * 240
        wave = (
            b"RIFF" + (36 + len(pcm)).to_bytes(4, "little") + b"WAVEfmt "
            + (16).to_bytes(4, "little") + (1).to_bytes(2, "little")
            + (1).to_bytes(2, "little") + (24_000).to_bytes(4, "little")
            + (48_000).to_bytes(4, "little") + (2).to_bytes(2, "little")
            + (16).to_bytes(2, "little") + b"data" + len(pcm).to_bytes(4, "little") + pcm
        )
        return TextToSpeechResult(
            audio_bytes=wave,
            audio_asset_reference=f"generated/{digest}.wav",
            content_type="audio/wav",
            duration_seconds=max(1, len(request.text.split()) / 2.5),
            provider_job_id=f"det-tts:{digest}",
            usage_units=len(request.text),
            model_reference="deterministic-tts",
            voice_reference=request.voice_reference,
            generation_status="SUCCEEDED",
        )

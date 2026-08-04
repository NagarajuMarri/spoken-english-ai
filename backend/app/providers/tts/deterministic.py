import hashlib
from backend.app.providers.tts.contracts import TextToSpeechResult


class DeterministicTextToSpeechProvider:
    name = "deterministic-tts"
    voices = {"supportive-neutral", "supportive-slow"}

    def __init__(self):
        self.calls = 0

    def synthesize(self, request):
        if request.voice_reference not in self.voices:
            raise ValueError("Unsupported voice.")
        self.calls += 1
        digest = hashlib.sha256(request.text.encode()).hexdigest()[:16]
        return TextToSpeechResult(
            audio_asset_reference=f"generated/{digest}.wav",
            content_type="audio/wav",
            duration_seconds=max(1, len(request.text.split()) / 2.5),
            provider_job_id=f"det-tts:{digest}",
            usage_units=len(request.text),
            generation_status="SUCCEEDED",
        )

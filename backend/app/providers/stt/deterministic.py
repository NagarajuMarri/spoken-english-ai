from backend.app.providers.stt.contracts import SpeechToTextResult


class DeterministicSpeechToTextProvider:
    name = "deterministic-stt"
    allowed_types = {"audio/wav", "audio/mpeg", "audio/webm"}

    def __init__(self, transcript="I enjoy practising English every day."):
        self.transcript = transcript
        self.calls = 0

    def transcribe(self, request):
        if request.content_type not in self.allowed_types:
            raise ValueError("Unsupported audio content type.")
        if request.duration_seconds > request.maximum_duration_seconds:
            raise ValueError("Audio duration exceeds limit.")
        self.calls += 1
        return SpeechToTextResult(
            transcript=self.transcript,
            detected_language=request.language_hint,
            confidence=0.99,
            provider_job_id=f"det-stt:{request.voice_turn_id}",
            duration_seconds=request.duration_seconds,
            usage_units=request.duration_seconds,
            processing_status="SUCCEEDED",
        )

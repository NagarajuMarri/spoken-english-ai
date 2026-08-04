from backend.app.ai.exceptions import ProviderTimeout, ProviderUnavailable
from backend.app.providers.tts.contracts import TextToSpeechResult


class OpenAICompatibleTTSProvider:
    def __init__(self, client, *, model: str, timeout_seconds=30, max_retries=2):
        if not model or not 0 <= max_retries <= 3:
            raise ValueError("Unsafe TTS configuration.")
        self.client, self.model = client, model
        self.timeout_seconds, self.max_retries = timeout_seconds, max_retries

    def synthesize(self, request):
        try:
            value = self.client.synthesize_metadata(
                model=self.model, text=request.text, voice=request.voice_reference,
                timeout=self.timeout_seconds, max_retries=self.max_retries,
            )
            return TextToSpeechResult.model_validate(value)
        except TimeoutError as exc:
            raise ProviderTimeout("Voice provider timed out.") from exc
        except Exception as exc:
            raise ProviderUnavailable("Voice provider unavailable.") from exc

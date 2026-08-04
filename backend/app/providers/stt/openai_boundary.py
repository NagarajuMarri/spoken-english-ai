from backend.app.ai.exceptions import ProviderTimeout, ProviderUnavailable
from backend.app.providers.stt.contracts import SpeechToTextResult


class OpenAICompatibleSTTProvider:
    def __init__(self, client, *, model: str, timeout_seconds=30, max_retries=2):
        if not model or not 0 <= max_retries <= 3:
            raise ValueError("Unsafe STT configuration.")
        self.client, self.model = client, model
        self.timeout_seconds, self.max_retries = timeout_seconds, max_retries

    def transcribe(self, request):
        try:
            value = self.client.transcribe(
                model=self.model,
                audio_reference=request.audio_asset_reference,
                timeout=self.timeout_seconds,
                max_retries=self.max_retries,
            )
            return SpeechToTextResult.model_validate(value)
        except TimeoutError as exc:
            raise ProviderTimeout("Speech provider timed out.") from exc
        except Exception as exc:
            raise ProviderUnavailable("Speech provider unavailable.") from exc

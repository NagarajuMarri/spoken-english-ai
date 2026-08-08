from backend.app.providers.tts.deterministic import DeterministicTextToSpeechProvider
from backend.app.providers.tts.openai_boundary import OpenAICompatibleTTSProvider, OpenAISpeechHTTPClient


def build_text_to_speech_provider(settings):
    if settings.text_to_speech_provider == "openai":
        return OpenAICompatibleTTSProvider(
            OpenAISpeechHTTPClient(settings.openai_api_key),
            model=settings.openai_tts_model,
            timeout_seconds=settings.openai_tts_timeout_seconds,
            max_retries=settings.openai_tts_max_retries,
            response_format=settings.openai_tts_response_format,
        )
    if settings.text_to_speech_provider == "fake":
        return DeterministicTextToSpeechProvider()
    return None

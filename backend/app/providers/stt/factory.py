from backend.app.providers.stt.deterministic import DeterministicSpeechToTextProvider
from backend.app.providers.stt.openai_boundary import OpenAICompatibleSTTProvider, OpenAITranscriptionHTTPClient


def build_speech_to_text_provider(settings):
    if settings.speech_to_text_provider == "openai":
        return OpenAICompatibleSTTProvider(
            OpenAITranscriptionHTTPClient(settings.openai_api_key),
            model=settings.openai_stt_model,
        )
    if settings.speech_to_text_provider == "fake":
        return DeterministicSpeechToTextProvider()
    return None

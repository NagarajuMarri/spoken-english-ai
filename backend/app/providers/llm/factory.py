from backend.app.ai.deterministic_provider import DeterministicAIProvider
from backend.app.providers.llm.openai_boundary import OpenAICompatibleAIProvider, OpenAIResponsesHTTPClient


def build_llm_provider(settings, *, fast: bool = False):
    if settings.llm_provider == "openai":
        return OpenAICompatibleAIProvider(
            OpenAIResponsesHTTPClient(settings.openai_api_key),
            model=settings.openai_llm_fast_model if fast else settings.openai_llm_model,
            timeout_seconds=settings.openai_llm_timeout_seconds,
            max_retries=settings.openai_llm_max_retries,
            reasoning_effort=settings.openai_llm_reasoning_effort,
            max_output_tokens=settings.openai_llm_max_output_tokens,
        )
    if settings.llm_provider == "fake":
        if settings.environment != "test":
            raise ValueError("The fake LLM provider is test-only.")
        return DeterministicAIProvider()
    return None

from backend.app.ai.exceptions import ProviderTimeout, ProviderUnavailable
from backend.app.ai.prompts import safe_prompt_context
from backend.app.ai.validation import validate_provider_output


class OpenAICompatibleAIProvider:
    """Injected-client boundary; it never reads keys or logs raw requests/responses."""
    name = "openai-compatible"

    def __init__(self, client, *, model: str, timeout_seconds: float = 20, max_retries: int = 2):
        if not model or max_retries < 0 or max_retries > 3:
            raise ValueError("Unsafe provider configuration.")
        self.client = client
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries

    def generate(self, request):
        try:
            value = self.client.generate_structured(
                model=self.model,
                context=safe_prompt_context(request),
                timeout=self.timeout_seconds,
                max_retries=self.max_retries,
            )
            return validate_provider_output(value)
        except TimeoutError as exc:
            raise ProviderTimeout("AI provider timed out.") from exc
        except ProviderTimeout:
            raise
        except Exception as exc:
            raise ProviderUnavailable("AI provider unavailable.") from exc

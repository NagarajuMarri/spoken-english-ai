from backend.app.language_review.deterministic import DeterministicLanguageReviewProvider
from backend.app.language_review.openai_boundary import (
    OpenAILanguageReviewHTTPClient,
    OpenAILanguageReviewProvider,
)


def build_language_review_provider(settings):
    if settings.language_review_provider == "openai":
        return OpenAILanguageReviewProvider(
            OpenAILanguageReviewHTTPClient(settings.openai_api_key),
            model=settings.openai_language_review_model,
            timeout_seconds=settings.openai_language_review_timeout_seconds,
            max_retries=settings.openai_language_review_max_retries,
            reasoning_effort=settings.openai_language_review_reasoning_effort,
            max_output_tokens=settings.openai_language_review_max_output_tokens,
        )
    if settings.language_review_provider == "fake":
        if settings.environment != "test":
            raise ValueError("The fake language reviewer is test-only.")
        return DeterministicLanguageReviewProvider()
    return None

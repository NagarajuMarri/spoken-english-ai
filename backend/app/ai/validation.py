from backend.app.ai.exceptions import ProviderOutputInvalid
from backend.app.ai.models import AIConversationResponse


def validate_provider_output(value) -> AIConversationResponse:
    try:
        return value if isinstance(value, AIConversationResponse) else AIConversationResponse.model_validate(value)
    except Exception as exc:
        raise ProviderOutputInvalid("Provider returned invalid structured output.") from exc

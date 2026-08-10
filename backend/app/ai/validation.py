import logging

from pydantic import ValidationError

from backend.app.ai.exceptions import ProviderOutputInvalid
from backend.app.ai.models import AIConversationResponse, LearningSignals, UsageInfo


_SAFE_SCHEMA_FIELDS = {
    *AIConversationResponse.model_fields,
    *LearningSignals.model_fields,
    *UsageInfo.model_fields,
}
logger = logging.getLogger("spoken_english.provider_validation")


def _safe_schema_path(location: tuple[object, ...]) -> str:
    parts = [
        str(part)
        if isinstance(part, int) or (isinstance(part, str) and part in _SAFE_SCHEMA_FIELDS)
        else "unexpected_field"
        for part in location
    ]
    return ".".join(parts) or "root"


def validate_provider_output(
    value,
    *,
    provider_requests: int = 1,
    input_units: int = 0,
    output_units: int = 0,
) -> AIConversationResponse:
    try:
        return value if isinstance(value, AIConversationResponse) else AIConversationResponse.model_validate(value)
    except ValidationError as exc:
        first_error = exc.errors(include_url=False, include_context=False, include_input=False)[0]
        schema_path = _safe_schema_path(tuple(first_error.get("loc", ())))
        logger.warning(
            "provider_output_validation_failed schema_path=%s error_type=%s",
            schema_path[:200],
            str(first_error.get("type", "unknown"))[:80],
        )
        raise ProviderOutputInvalid(
            "Provider returned invalid structured output.",
            provider_requests=provider_requests,
            input_units=input_units,
            output_units=output_units,
            schema_path=schema_path[:200],
        ) from exc
    except (TypeError, ValueError) as exc:
        raise ProviderOutputInvalid(
            "Provider returned invalid structured output.",
            provider_requests=provider_requests,
            input_units=input_units,
            output_units=output_units,
            schema_path="root",
        ) from exc

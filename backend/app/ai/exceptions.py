class ProviderError(Exception):
    """Privacy-safe provider failure base with bounded-attempt metadata."""

    failure_code = "provider_unavailable"
    retryable = False

    def __init__(
        self,
        message: str,
        *,
        provider_requests: int = 1,
        retry_after_seconds: int | None = None,
    ) -> None:
        super().__init__(message)
        self.provider_requests = max(1, provider_requests)
        self.retry_after_seconds = retry_after_seconds


class ProviderUnavailable(ProviderError):
    pass


class ProviderTimeout(ProviderError):
    failure_code = "provider_timeout"
    retryable = True


class ProviderConnectionError(ProviderError):
    failure_code = "provider_connection_error"
    retryable = True


class ProviderRateLimited(ProviderError):
    failure_code = "provider_rate_limit"
    retryable = True


class ProviderServiceError(ProviderError):
    failure_code = "provider_service_error"
    retryable = True


class ProviderContextLimit(ProviderError):
    failure_code = "provider_context_limit"


class ProviderMalformedResponse(ProviderError):
    failure_code = "provider_malformed_response"


class ProviderOutputInvalid(ProviderError):
    failure_code = "provider_schema_validation_failed"

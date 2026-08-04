"""Deterministic, mock, and non-invoking real-provider boundaries."""

from __future__ import annotations

from typing import Protocol

from backend.app.provider_sandbox.models import (
    ErrorCode, ProviderCapability, ProviderConfiguration, ProviderError,
    ProviderHealth, SandboxRequest,
)


class SandboxProvider(Protocol):
    provider_id: str
    capabilities: tuple[ProviderCapability, ...]

    def execute(self, request: SandboxRequest) -> tuple[dict, float, float]: ...
    def health(self) -> ProviderHealth: ...


class DeterministicSandboxProvider:
    provider_id = "deterministic-local"
    capabilities = tuple(ProviderCapability)

    def execute(self, request: SandboxRequest) -> tuple[dict, float, float]:
        return ({"status": "deterministic", "request_id": request.request_id}, 7, 0)

    def health(self) -> ProviderHealth:
        return ProviderHealth.HEALTHY


class MockSandboxProvider:
    def __init__(
        self,
        provider_id: str,
        capabilities: tuple[ProviderCapability, ...],
        *,
        latency_ms: float = 20,
        cost_usd: float = 0,
        fail: bool = False,
    ):
        self.provider_id, self.capabilities = provider_id, capabilities
        self.latency_ms, self.cost_usd, self.fail = latency_ms, cost_usd, fail

    def execute(self, request: SandboxRequest) -> tuple[dict, float, float]:
        if self.fail:
            raise ProviderError(
                ErrorCode.PROVIDER_FAILURE,
                self.provider_id,
                "controlled mock failure",
                True,
            )
        return (
            {"status": "mock", "request_id": request.request_id},
            self.latency_ms,
            self.cost_usd,
        )

    def health(self) -> ProviderHealth:
        return ProviderHealth.DEGRADED if self.fail else ProviderHealth.HEALTHY


class RealProviderBoundary:
    """Validates production wiring without making a network call."""

    def __init__(self, configuration: ProviderConfiguration):
        self.provider_id, self.capabilities = (
            configuration.provider_id,
            configuration.capabilities,
        )

    def execute(self, request: SandboxRequest) -> tuple[dict, float, float]:
        raise ProviderError(
            ErrorCode.DISABLED,
            self.provider_id,
            "live invocation requires a separate human-approved adapter",
            False,
        )

    def health(self) -> ProviderHealth:
        return ProviderHealth.DISABLED

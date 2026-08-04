"""Registry, fallback, limits, circuit breaking, metering, and health."""

from __future__ import annotations

import os
from collections import defaultdict

from backend.app.provider_sandbox.models import *
from backend.app.provider_sandbox.providers import SandboxProvider


class ProviderSandboxService:
    def __init__(
        self,
        limits: SandboxLimits,
        *,
        sandbox_mode: bool = True,
        failure_threshold: int = 3,
    ):
        if not sandbox_mode:
            raise ValueError("Milestone 9 permits sandbox mode only")
        self.limits, self.failure_threshold = limits, failure_threshold
        self._providers: dict[str, SandboxProvider] = {}
        self._configurations: dict[str, ProviderConfiguration] = {}
        self._routes: dict[ProviderCapability, list[str]] = defaultdict(list)
        self._usage: list[UsageRecord] = []
        self._failures: dict[str, int] = defaultdict(int)
        self._disabled: set[str] = set()

    def register(
        self, configuration: ProviderConfiguration, provider: SandboxProvider
    ) -> None:
        if (
            configuration.provider_id != provider.provider_id
            or configuration.provider_id in self._providers
        ):
            raise ValueError("Provider identity must be unique and consistent")
        if set(configuration.capabilities) != set(provider.capabilities):
            raise ValueError("Discovered capabilities differ from configuration")
        if configuration.mode is ProviderMode.REAL_BOUNDARY and not os.getenv(
            configuration.credential_env_var or ""
        ):
            raise ProviderError(
                ErrorCode.MISSING_CREDENTIAL,
                configuration.provider_id,
                "credential environment variable is not set",
                False,
            )
        self._providers[provider.provider_id] = provider
        self._configurations[provider.provider_id] = configuration
        for capability in configuration.capabilities:
            self._routes[capability].append(provider.provider_id)

    def discover(self, provider_id: str) -> tuple[ProviderCapability, ...]:
        return self._configurations[provider_id].capabilities

    def disable(self, provider_id: str) -> None:
        self._disabled.add(provider_id)

    def enable(self, provider_id: str) -> None:
        self._disabled.discard(provider_id)

    def execute(self, request: SandboxRequest) -> ProviderResult:
        self._validate_limits(request)
        errors = []
        for index, provider_id in enumerate(self._routes.get(request.capability, ())):
            if (
                provider_id in self._disabled
                or self._failures[provider_id] >= self.failure_threshold
            ):
                continue
            provider = self._providers[provider_id]
            config = self._configurations[provider_id]
            for attempt in range(config.maximum_retries + 1):
                try:
                    payload, latency, cost = provider.execute(request)
                    if latency > config.timeout_seconds * 1000:
                        raise ProviderError(
                            ErrorCode.TIMEOUT, provider_id, "provider timeout", True
                        )
                    self._validate_cost(request.user_id, cost)
                    usage = UsageRecord(
                        request.request_id,
                        request.user_id,
                        provider_id,
                        request.capability,
                        request.input_units,
                        0,
                        cost,
                        latency,
                    )
                    self._usage.append(usage)
                    self._failures[provider_id] = 0
                    return ProviderResult(
                        provider_id, request.capability, payload, usage, index > 0
                    )
                except ProviderError as error:
                    errors.append(error)
                    self._failures[provider_id] += 1
                    if not error.retryable or attempt == config.maximum_retries:
                        break
        if errors:
            raise errors[-1]
        raise ProviderError(
            ErrorCode.DISABLED, "none", "no enabled healthy provider", False
        )

    def usage_report(self) -> tuple[UsageRecord, ...]:
        return tuple(self._usage)

    def health_report(self) -> tuple[HealthReport, ...]:
        values = []
        for provider_id, provider in sorted(self._providers.items()):
            status = (
                ProviderHealth.DISABLED
                if provider_id in self._disabled
                else (
                    ProviderHealth.OPEN
                    if self._failures[provider_id] >= self.failure_threshold
                    else provider.health()
                )
            )
            latencies = [
                item.latency_ms
                for item in self._usage
                if item.provider_id == provider_id
            ]
            values.append(
                HealthReport(
                    provider_id,
                    status,
                    self._failures[provider_id],
                    latencies[-1] if latencies else None,
                )
            )
        return tuple(values)

    def _validate_limits(self, request: SandboxRequest) -> None:
        if (
            request.tokens > self.limits.per_request_tokens
            or request.audio_seconds > self.limits.per_request_audio_seconds
        ):
            raise ProviderError(
                ErrorCode.LIMIT_EXCEEDED, "sandbox", "request limit exceeded", False
            )
        user = [item for item in self._usage if item.user_id == request.user_id]
        if (
            len(self._usage) >= self.limits.daily_requests
            or len(user) >= self.limits.per_user_requests
        ):
            raise ProviderError(
                ErrorCode.LIMIT_EXCEEDED, "sandbox", "request count exceeded", False
            )
        total = sum(item.cost_usd for item in self._usage)
        user_total = sum(item.cost_usd for item in user)
        if (
            total >= self.limits.daily_budget_usd
            or total >= self.limits.monthly_budget_usd
            or user_total >= self.limits.per_user_budget_usd
        ):
            raise ProviderError(
                ErrorCode.BUDGET_EXCEEDED, "sandbox", "budget exceeded", False
            )

    def _validate_cost(self, user_id: str, cost: float) -> None:
        total = sum(item.cost_usd for item in self._usage)
        user_total = sum(
            item.cost_usd for item in self._usage if item.user_id == user_id
        )
        if (
            cost < 0
            or total + cost > self.limits.daily_budget_usd
            or total + cost > self.limits.monthly_budget_usd
            or user_total + cost > self.limits.per_user_budget_usd
        ):
            raise ProviderError(
                ErrorCode.BUDGET_EXCEEDED,
                "sandbox",
                "projected cost exceeds budget",
                False,
            )

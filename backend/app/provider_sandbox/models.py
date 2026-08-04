"""Immutable provider-sandbox contracts and evidence values."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


def utc_now() -> datetime:
    return datetime.now(UTC)


class ProviderCapability(str, Enum):
    LLM = "LLM"
    SPEECH_TO_TEXT = "SPEECH_TO_TEXT"
    TEXT_TO_SPEECH = "TEXT_TO_SPEECH"
    AVATAR_TIMING = "AVATAR_TIMING"
    USAGE_METERING = "USAGE_METERING"
    HEALTH = "HEALTH"


class ProviderMode(str, Enum):
    DETERMINISTIC = "DETERMINISTIC"
    MOCK = "MOCK"
    REAL_BOUNDARY = "REAL_BOUNDARY"


class ProviderHealth(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    OPEN = "OPEN"
    DISABLED = "DISABLED"


class ErrorCode(str, Enum):
    DISABLED = "DISABLED"
    INVALID_ENVIRONMENT = "INVALID_ENVIRONMENT"
    MISSING_CREDENTIAL = "MISSING_CREDENTIAL"
    TIMEOUT = "TIMEOUT"
    RATE_LIMITED = "RATE_LIMITED"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    LIMIT_EXCEEDED = "LIMIT_EXCEEDED"
    CIRCUIT_OPEN = "CIRCUIT_OPEN"
    PROVIDER_FAILURE = "PROVIDER_FAILURE"


@dataclass(frozen=True)
class ProviderConfiguration:
    provider_id: str
    mode: ProviderMode
    capabilities: tuple[ProviderCapability, ...]
    environment: str = "sandbox"
    credential_env_var: str | None = None
    enabled: bool = True
    timeout_seconds: float = 10
    maximum_retries: int = 2
    base_delay_seconds: float = 0.1
    metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not self.provider_id.strip() or not self.capabilities:
            raise ValueError("Provider identity and capabilities are required")
        if self.environment not in {"sandbox", "test"}:
            raise ValueError("Only sandbox or test environments are allowed")
        if (
            self.timeout_seconds <= 0
            or not 0 <= self.maximum_retries <= 5
            or self.base_delay_seconds < 0
        ):
            raise ValueError("Provider policies must be bounded")
        if self.mode is ProviderMode.REAL_BOUNDARY and not self.credential_env_var:
            raise ValueError("Real boundary requires an environment-key reference")


@dataclass(frozen=True)
class SandboxLimits:
    daily_budget_usd: float
    monthly_budget_usd: float
    per_user_budget_usd: float
    daily_requests: int
    per_user_requests: int
    per_request_tokens: int
    per_request_audio_seconds: float

    def __post_init__(self) -> None:
        values = (
            self.daily_budget_usd,
            self.monthly_budget_usd,
            self.per_user_budget_usd,
            self.daily_requests,
            self.per_user_requests,
            self.per_request_tokens,
            self.per_request_audio_seconds,
        )
        if any(value <= 0 for value in values):
            raise ValueError("Sandbox limits must be positive")
        if (
            self.daily_budget_usd > self.monthly_budget_usd
            or self.per_user_budget_usd > self.daily_budget_usd
        ):
            raise ValueError("Sandbox budgets must be hierarchically bounded")


@dataclass(frozen=True)
class SandboxRequest:
    request_id: str
    user_id: str
    capability: ProviderCapability
    input_units: float = 0
    tokens: int = 0
    audio_seconds: float = 0


@dataclass(frozen=True)
class UsageRecord:
    request_id: str
    user_id: str
    provider_id: str
    capability: ProviderCapability
    input_units: float
    output_units: float
    cost_usd: float
    latency_ms: float
    recorded_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class ProviderResult:
    provider_id: str
    capability: ProviderCapability
    payload: dict[str, Any]
    usage: UsageRecord
    fallback_used: bool = False


@dataclass(frozen=True)
class ProviderError(Exception):
    code: ErrorCode
    provider_id: str
    message: str
    retryable: bool

    def __str__(self) -> str:
        return f"{self.code.value}:{self.provider_id}:{self.message}"


@dataclass(frozen=True)
class HealthReport:
    provider_id: str
    status: ProviderHealth
    failure_count: int
    latency_ms: float | None
    checked_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class ProviderEvidence:
    evidence_id: str
    provider_id: str
    category: str
    offering: str
    quality: str
    latency: str
    pricing: str
    limits: str
    sdk_maturity: str
    documentation_url: str
    licensing: str
    advantages: tuple[str, ...]
    limitations: tuple[str, ...]
    integration_complexity: str
    privacy: str
    production_readiness: str
    estimated_monthly_cost_usd: float | None
    estimated_cost_per_learner_usd: float | None
    collected_at: datetime


@dataclass(frozen=True)
class EvaluationReport:
    report_id: str
    category: str
    evidence_ids: tuple[str, ...]
    expected_latency: str
    expected_quality: str
    estimated_budget_usd: float
    known_risks: tuple[str, ...]


@dataclass(frozen=True)
class HumanDecisionPackage:
    package_id: str
    evidence_as_of: datetime
    llm: str
    stt: str
    female_voice: str
    male_voice: str
    avatar_timing: str
    pilot_budget_usd: float
    usage_limits: SandboxLimits
    supported_browsers: tuple[str, ...]
    go_no_go: str
    evidence_ids: tuple[str, ...]
    automatic_selection: bool = False

"""Offline provider registration, fallback, metering, and decision-package example."""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.provider_sandbox import (
    ProviderCapability, ProviderConfiguration, ProviderMode,
    ProviderSandboxService, SandboxLimits, SandboxRequest,
)
from backend.app.provider_sandbox.providers import (
    DeterministicSandboxProvider,
    MockSandboxProvider,
)

limits = SandboxLimits(10, 150, 7.5, 100, 10, 4096, 120)
service = ProviderSandboxService(limits)
failed = MockSandboxProvider("mock-failure", tuple(ProviderCapability), fail=True)
local = DeterministicSandboxProvider()
for provider, mode, retries in (
    (failed, ProviderMode.MOCK, 0),
    (local, ProviderMode.DETERMINISTIC, 0),
):
    service.register(
        ProviderConfiguration(
            provider.provider_id, mode, provider.capabilities, maximum_retries=retries
        ),
        provider,
    )
result = service.execute(
    SandboxRequest("demo-1", "learner-1", ProviderCapability.LLM, tokens=50)
)
package = json.loads(
    Path("docs/HUMAN_DECISION_PACKAGE_PM9.json").read_text(encoding="utf-8")
)
print(
    f"provider={result.provider_id} fallback={str(result.fallback_used).lower()} cost={result.usage.cost_usd:.2f}"
)
print(f"health={','.join(item.status.value for item in service.health_report())}")
print(f"decision_package={package['package_id']} status={package['status']}")
print(
    f"live_provider=false generated_at={datetime(2026, 8, 4, tzinfo=UTC).isoformat()}"
)

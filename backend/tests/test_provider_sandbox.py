import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from backend.app.provider_sandbox import *
from backend.app.provider_sandbox.evaluation import (
    build_human_package,
    comparison_matrix,
    evaluation_report,
)
from backend.app.provider_sandbox.providers import (
    DeterministicSandboxProvider,
    MockSandboxProvider,
    RealProviderBoundary,
)


def limits(**changes):
    values = {
        "daily_budget_usd": 10,
        "monthly_budget_usd": 150,
        "per_user_budget_usd": 7.5,
        "daily_requests": 100,
        "per_user_requests": 10,
        "per_request_tokens": 4096,
        "per_request_audio_seconds": 120,
    }
    values.update(changes)
    return SandboxLimits(**values)


def configuration(provider, mode=ProviderMode.MOCK, **changes):
    values = {
        "provider_id": provider.provider_id,
        "mode": mode,
        "capabilities": provider.capabilities,
        "maximum_retries": 0,
    }
    values.update(changes)
    return ProviderConfiguration(**values)


def request(**changes):
    values = {
        "request_id": "request-1",
        "user_id": "learner-1",
        "capability": ProviderCapability.LLM,
        "tokens": 100,
    }
    values.update(changes)
    return SandboxRequest(**values)


def test_sandbox_mode_is_mandatory():
    with pytest.raises(ValueError):
        ProviderSandboxService(limits(), sandbox_mode=False)


def test_configuration_rejects_production_environment_and_unbounded_policy():
    provider = DeterministicSandboxProvider()
    with pytest.raises(ValueError):
        configuration(provider, ProviderMode.DETERMINISTIC, environment="production")
    with pytest.raises(ValueError):
        configuration(provider, ProviderMode.DETERMINISTIC, maximum_retries=6)


def test_registration_and_capability_discovery():
    provider = DeterministicSandboxProvider()
    service = ProviderSandboxService(limits())
    service.register(configuration(provider, ProviderMode.DETERMINISTIC), provider)
    assert service.discover(provider.provider_id) == tuple(ProviderCapability)
    with pytest.raises(ValueError):
        service.register(configuration(provider, ProviderMode.DETERMINISTIC), provider)


def test_real_boundary_loads_key_only_from_environment(monkeypatch):
    config = ProviderConfiguration(
        "real",
        ProviderMode.REAL_BOUNDARY,
        (ProviderCapability.LLM,),
        credential_env_var="TEST_PROVIDER_KEY",
    )
    service = ProviderSandboxService(limits())
    boundary = RealProviderBoundary(config)
    with pytest.raises(ProviderError) as error:
        service.register(config, boundary)
    assert error.value.code is ErrorCode.MISSING_CREDENTIAL and "secret" not in str(
        error.value
    )
    monkeypatch.setenv("TEST_PROVIDER_KEY", "secret-value")
    service.register(config, boundary)
    assert service.discover("real") == (ProviderCapability.LLM,)


def test_deterministic_execution_records_usage_and_latency():
    provider = DeterministicSandboxProvider()
    service = ProviderSandboxService(limits())
    service.register(configuration(provider, ProviderMode.DETERMINISTIC), provider)
    result = service.execute(request())
    assert result.usage.latency_ms == 7 and result.usage.cost_usd == 0
    assert service.usage_report() == (result.usage,)


def test_provider_fallback_is_structured_and_deterministic():
    failed = MockSandboxProvider("failed", (ProviderCapability.LLM,), fail=True)
    healthy = MockSandboxProvider("healthy", (ProviderCapability.LLM,), cost_usd=0.1)
    service = ProviderSandboxService(limits())
    service.register(configuration(failed), failed)
    service.register(configuration(healthy), healthy)
    result = service.execute(request())
    assert result.provider_id == "healthy" and result.fallback_used


def test_timeout_is_structured_and_opens_circuit():
    slow = MockSandboxProvider("slow", (ProviderCapability.LLM,), latency_ms=2000)
    service = ProviderSandboxService(limits(), failure_threshold=1)
    service.register(configuration(slow, timeout_seconds=1), slow)
    with pytest.raises(ProviderError) as error:
        service.execute(request())
    assert error.value.code is ErrorCode.TIMEOUT
    assert service.health_report()[0].status is ProviderHealth.OPEN


def test_disable_switch_prevents_invocation():
    provider = DeterministicSandboxProvider()
    service = ProviderSandboxService(limits())
    service.register(configuration(provider, ProviderMode.DETERMINISTIC), provider)
    service.disable(provider.provider_id)
    with pytest.raises(ProviderError) as error:
        service.execute(request())
    assert error.value.code is ErrorCode.DISABLED


@pytest.mark.parametrize("changes", [{"tokens": 4097}, {"audio_seconds": 121}])
def test_per_request_limits(changes):
    provider = DeterministicSandboxProvider()
    service = ProviderSandboxService(limits())
    service.register(configuration(provider, ProviderMode.DETERMINISTIC), provider)
    with pytest.raises(ProviderError) as error:
        service.execute(request(**changes))
    assert error.value.code is ErrorCode.LIMIT_EXCEEDED


def test_request_and_user_count_limits():
    provider = DeterministicSandboxProvider()
    service = ProviderSandboxService(limits(per_user_requests=1))
    service.register(configuration(provider, ProviderMode.DETERMINISTIC), provider)
    service.execute(request())
    with pytest.raises(ProviderError):
        service.execute(request(request_id="request-2"))


def test_projected_cost_cannot_cross_budget():
    provider = MockSandboxProvider("costly", (ProviderCapability.LLM,), cost_usd=8)
    service = ProviderSandboxService(limits())
    service.register(configuration(provider), provider)
    with pytest.raises(ProviderError) as error:
        service.execute(request())
    assert (
        error.value.code is ErrorCode.BUDGET_EXCEEDED and service.usage_report() == ()
    )


def evidence(identifier="e-1", category="LLM", provider="provider"):
    return ProviderEvidence(
        identifier,
        provider,
        category,
        "offering",
        "quality",
        "latency",
        "pricing",
        "limits",
        "sdk",
        "https://example.test/docs",
        "license",
        ("advantage",),
        ("limitation",),
        "LOW",
        "privacy",
        "SHORTLIST",
        1,
        0.1,
        datetime(2026, 8, 4, tzinfo=UTC),
    )


def test_matrix_is_deterministic_and_rejects_duplicate_evidence():
    first = evidence("b", "STT", "z")
    second = evidence("a", "LLM", "a")
    assert comparison_matrix((first, second)) == (second, first)
    with pytest.raises(ValueError):
        comparison_matrix((first, first))


def test_evaluation_report_requires_category_evidence():
    report = evaluation_report("report-1", "LLM", (evidence(),), 150)
    assert report.evidence_ids == ("e-1",) and report.estimated_budget_usd == 150
    with pytest.raises(ValueError):
        evaluation_report("report-2", "TTS", (evidence(),), 150)


def test_human_package_never_automatically_selects():
    package = build_human_package(
        "decision-1",
        (evidence(),),
        limits(),
        budget=150,
        as_of=datetime(2026, 8, 4, tzinfo=UTC),
    )
    assert not package.automatic_selection and package.go_no_go.startswith("NO_GO")


def test_evidence_and_decision_artifacts_are_complete():
    matrix = json.loads(
        Path("docs/PROVIDER_SANDBOX_EVIDENCE.json").read_text(encoding="utf-8")
    )
    package = json.loads(
        Path("docs/HUMAN_DECISION_PACKAGE_PM9.json").read_text(encoding="utf-8")
    )
    assert len({item["provider_id"] for item in matrix["providers"]}) == 5
    assert (
        len(matrix["providers"]) == 7
        and matrix["cost_model"]["provisional_monthly_ceiling_usd"] == 150
    )
    assert package["package_id"] == "spoken-english-ai-pm9-provider-decision-v1"
    assert (
        package["status"] == "WAITING_FOR_HUMAN_REVIEW"
        and not package["automatic_selection"]
    )

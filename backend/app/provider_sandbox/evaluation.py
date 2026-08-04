"""Deterministic evidence matrix, reports, budget, and human package."""

from __future__ import annotations

from datetime import datetime

from backend.app.provider_sandbox.models import (
    EvaluationReport, HumanDecisionPackage, ProviderEvidence, SandboxLimits,
)


def comparison_matrix(
    evidence: tuple[ProviderEvidence, ...],
) -> tuple[ProviderEvidence, ...]:
    ids = [item.evidence_id for item in evidence]
    if len(ids) != len(set(ids)):
        raise ValueError("Evidence IDs must be unique")
    return tuple(
        sorted(
            evidence, key=lambda item: (item.category, item.provider_id, item.offering)
        )
    )


def evaluation_report(
    report_id: str, category: str, evidence: tuple[ProviderEvidence, ...], budget: float
) -> EvaluationReport:
    selected = tuple(
        item for item in comparison_matrix(evidence) if item.category == category
    )
    if not selected:
        raise ValueError("Evaluation requires evidence")
    return EvaluationReport(
        report_id,
        category,
        tuple(item.evidence_id for item in selected),
        "must be measured in sandbox",
        "must pass Indian-English cohort scoring",
        budget,
        (
            "prices and limits may change",
            "quality requires controlled human evaluation",
        ),
    )


def build_human_package(
    package_id: str,
    evidence: tuple[ProviderEvidence, ...],
    limits: SandboxLimits,
    *,
    budget: float,
    as_of: datetime,
) -> HumanDecisionPackage:
    ids = tuple(item.evidence_id for item in comparison_matrix(evidence))
    return HumanDecisionPackage(
        package_id,
        as_of,
        "OpenAI-compatible LLM shortlist — human decision required",
        "Deepgram Nova-3 en-IN shortlist — human validation required",
        "Azure en-IN-NeerjaNeural shortlist — listening test required",
        "Azure en-IN-PrabhatNeural shortlist — listening test required",
        "Azure viseme IDs when locale-supported; approximate local fallback",
        budget,
        limits,
        ("Chrome current", "Edge current", "Firefox current", "Safari current"),
        "NO_GO pending credential, privacy, quality, latency and budget approval",
        ids,
        False,
    )

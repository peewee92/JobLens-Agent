"""Deterministic SkillGap metric calculation from TargetCohort/Profile facts."""
from __future__ import annotations

import pytest

from app.application.target_cohort_profile_comparison import (
    ProfileCapabilityCoverageStatus,
    TargetCohortProfileCapabilityComparison,
    TargetCohortProfileComparisonResult,
)
from app.application.target_cohort_skill_gap_metrics import (
    CalculateTargetCohortSkillGapMetricsUseCase,
)


def _comparison(
    capability: str,
    *,
    status: ProfileCapabilityCoverageStatus,
    requirement_ids: tuple[str, ...],
    job_ids: tuple[str, ...],
    must_have_count: int,
    preferred_count: int = 0,
    bonus_count: int = 0,
    evidence_ids: tuple[str, ...] = (),
) -> TargetCohortProfileCapabilityComparison:
    return TargetCohortProfileCapabilityComparison(
        capability=capability,
        status=status,
        requirement_ids=requirement_ids,
        job_ids=job_ids,
        requirement_count=len(requirement_ids),
        job_count=len(job_ids),
        must_have_count=must_have_count,
        preferred_count=preferred_count,
        bonus_count=bonus_count,
        profile_skill_ids=() if status is ProfileCapabilityCoverageStatus.MISSING else (f"skill_{capability}",),
        evidence_ids=evidence_ids,
    )


def _result(*items: TargetCohortProfileCapabilityComparison) -> TargetCohortProfileComparisonResult:
    return TargetCohortProfileComparisonResult(
        cohort_id="cohort_1",
        job_ids=("job_1", "job_2", "job_3", "job_4"),
        facts_usable=True,
        profile_id="profile_1",
        profile_version=3,
        capabilities=items,
    )


def test_metrics_use_market_coverage_importance_and_evidence_deficit() -> None:
    result = CalculateTargetCohortSkillGapMetricsUseCase().execute(
        _result(
            _comparison(
                "Kafka",
                status=ProfileCapabilityCoverageStatus.MISSING,
                requirement_ids=("req_1", "req_2", "req_3"),
                job_ids=("job_1", "job_2", "job_3"),
                must_have_count=2,
                preferred_count=1,
            ),
            _comparison(
                "React",
                status=ProfileCapabilityCoverageStatus.EVIDENCED,
                requirement_ids=("req_4", "req_5"),
                job_ids=("job_1", "job_2"),
                must_have_count=2,
                evidence_ids=("evidence_react",),
            ),
            _comparison(
                "FastAPI",
                status=ProfileCapabilityCoverageStatus.UNEVIDENCED,
                requirement_ids=("req_6",),
                job_ids=("job_4",),
                must_have_count=1,
            ),
        )
    )

    assert result.facts_usable is True
    assert result.profile_version == 3
    assert [item.capability for item in result.items] == ["Kafka", "React", "FastAPI"]

    kafka, react, fastapi = result.items
    assert kafka.target_coverage == 0.75
    assert kafka.must_have_ratio == pytest.approx(2 / 3, abs=1e-6)
    assert kafka.evidence_coverage == 0.0
    assert kafka.gap_severity == 0.625
    assert kafka.supporting_requirement_ids == ("req_1", "req_2", "req_3")

    assert react.target_coverage == 0.5
    assert react.must_have_ratio == 1.0
    assert react.evidence_coverage == 1.0
    assert react.gap_severity == 0.0

    assert fastapi.target_coverage == 0.25
    assert fastapi.must_have_ratio == 1.0
    assert fastapi.evidence_coverage == 0.0
    assert fastapi.gap_severity == 0.125


def test_unusable_comparison_fails_closed() -> None:
    comparison = TargetCohortProfileComparisonResult(
        cohort_id="cohort_1",
        job_ids=("job_1",),
        facts_usable=False,
        profile_id="profile_1",
        profile_version=3,
        capabilities=(),
    )

    result = CalculateTargetCohortSkillGapMetricsUseCase().execute(comparison)

    assert result.facts_usable is False
    assert result.items == ()
    assert result.db_writes == 0
    assert result.provider_calls == 0
    assert result.trace_runs_created == 0


def test_empty_cohort_fails_closed_instead_of_dividing_by_zero() -> None:
    comparison = TargetCohortProfileComparisonResult(
        cohort_id="cohort_empty",
        job_ids=(),
        facts_usable=True,
        profile_id="profile_1",
        profile_version=3,
        capabilities=(),
    )

    result = CalculateTargetCohortSkillGapMetricsUseCase().execute(comparison)

    assert result.facts_usable is False
    assert result.blockers == ("empty_target_cohort",)

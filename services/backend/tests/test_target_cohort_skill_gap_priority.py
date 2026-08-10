"""Deterministic P0/P1 prioritization for TargetCohort SkillGap metrics."""
from __future__ import annotations

from app.application.target_cohort_profile_comparison import ProfileCapabilityCoverageStatus
from app.application.target_cohort_skill_gap_metrics import (
    TargetCohortSkillGapMetric,
    TargetCohortSkillGapMetricsResult,
)
from app.application.target_cohort_skill_gap_priority import (
    PrioritizeTargetCohortSkillGapsUseCase,
    SkillGapPriority,
)


def _metric(
    capability: str,
    *,
    status: ProfileCapabilityCoverageStatus,
    target_coverage: float,
    must_have_ratio: float,
    evidence_coverage: float,
    gap_severity: float,
) -> TargetCohortSkillGapMetric:
    return TargetCohortSkillGapMetric(
        capability=capability,
        coverage_status=status,
        target_coverage=target_coverage,
        must_have_ratio=must_have_ratio,
        evidence_coverage=evidence_coverage,
        gap_severity=gap_severity,
        supporting_requirement_ids=(f"req_{capability}",),
        supporting_job_ids=(f"job_{capability}",),
        profile_skill_ids=() if status is ProfileCapabilityCoverageStatus.MISSING else (f"skill_{capability}",),
        evidence_ids=() if evidence_coverage == 0 else (f"evidence_{capability}",),
    )


def _result(*items: TargetCohortSkillGapMetric) -> TargetCohortSkillGapMetricsResult:
    return TargetCohortSkillGapMetricsResult(
        cohort_id="cohort_1",
        job_ids=("job_1", "job_2", "job_3", "job_4"),
        facts_usable=True,
        profile_id="profile_1",
        profile_version=3,
        items=items,
    )


def test_prioritization_excludes_evidenced_non_gaps_and_sorts_by_severity() -> None:
    result = PrioritizeTargetCohortSkillGapsUseCase().execute(
        _result(
            _metric(
                "FastAPI",
                status=ProfileCapabilityCoverageStatus.UNEVIDENCED,
                target_coverage=0.5,
                must_have_ratio=1.0,
                evidence_coverage=0.0,
                gap_severity=0.25,
            ),
            _metric(
                "React",
                status=ProfileCapabilityCoverageStatus.EVIDENCED,
                target_coverage=1.0,
                must_have_ratio=1.0,
                evidence_coverage=1.0,
                gap_severity=0.0,
            ),
            _metric(
                "Kafka",
                status=ProfileCapabilityCoverageStatus.MISSING,
                target_coverage=0.75,
                must_have_ratio=2 / 3,
                evidence_coverage=0.0,
                gap_severity=0.625,
            ),
        )
    )

    assert result.facts_usable is True
    assert [item.capability for item in result.items] == ["Kafka", "FastAPI"]
    assert [item.priority for item in result.items] == [SkillGapPriority.P0, SkillGapPriority.P1]
    assert result.items[0].supporting_requirement_ids == ("req_Kafka",)
    assert result.items[0].supporting_job_ids == ("job_Kafka",)
    assert result.db_writes == 0
    assert result.provider_calls == 0
    assert result.trace_runs_created == 0


def test_priority_is_derived_from_gap_severity_not_market_frequency_alone() -> None:
    result = PrioritizeTargetCohortSkillGapsUseCase().execute(
        _result(
            _metric(
                "HighFrequencyButUnevidenced",
                status=ProfileCapabilityCoverageStatus.UNEVIDENCED,
                target_coverage=1.0,
                must_have_ratio=0.0,
                evidence_coverage=0.0,
                gap_severity=0.25,
            ),
            _metric(
                "LowerFrequencyMustHaveMissing",
                status=ProfileCapabilityCoverageStatus.MISSING,
                target_coverage=0.75,
                must_have_ratio=1.0,
                evidence_coverage=0.0,
                gap_severity=0.75,
            ),
        )
    )

    assert result.items[0].capability == "LowerFrequencyMustHaveMissing"
    assert result.items[0].priority is SkillGapPriority.P0
    assert result.items[1].priority is SkillGapPriority.P1


def test_unusable_metrics_fail_closed_without_partial_priority_output() -> None:
    metrics = TargetCohortSkillGapMetricsResult(
        cohort_id="cohort_blocked",
        job_ids=("job_1",),
        facts_usable=False,
        profile_id="profile_1",
        profile_version=3,
        items=(),
        blockers=("requirements_not_released",),
    )

    result = PrioritizeTargetCohortSkillGapsUseCase().execute(metrics)

    assert result.facts_usable is False
    assert result.items == ()
    assert result.blockers == ("requirements_not_released",)

"""Deterministic SkillGap metrics from released TargetCohort/Profile facts."""
from __future__ import annotations

from dataclasses import dataclass

from app.application.target_cohort_profile_comparison import (
    ProfileCapabilityCoverageStatus,
    TargetCohortProfileComparisonResult,
)


_EVIDENCE_COVERAGE = {
    ProfileCapabilityCoverageStatus.EVIDENCED: 1.0,
    ProfileCapabilityCoverageStatus.UNEVIDENCED: 0.0,
    ProfileCapabilityCoverageStatus.MISSING: 0.0,
}

_GAP_DEFICIT_WEIGHT = {
    ProfileCapabilityCoverageStatus.EVIDENCED: 0.0,
    ProfileCapabilityCoverageStatus.UNEVIDENCED: 0.5,
    ProfileCapabilityCoverageStatus.MISSING: 1.0,
}


@dataclass(frozen=True, slots=True)
class TargetCohortSkillGapMetric:
    capability: str
    coverage_status: ProfileCapabilityCoverageStatus
    target_coverage: float
    must_have_ratio: float
    evidence_coverage: float
    gap_severity: float
    supporting_requirement_ids: tuple[str, ...]
    supporting_job_ids: tuple[str, ...]
    profile_skill_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TargetCohortSkillGapMetricsResult:
    cohort_id: str
    job_ids: tuple[str, ...]
    facts_usable: bool
    profile_id: str | None
    profile_version: int | None
    items: tuple[TargetCohortSkillGapMetric, ...]
    blockers: tuple[str, ...] = ()
    db_writes: int = 0
    provider_calls: int = 0
    trace_runs_created: int = 0


class CalculateTargetCohortSkillGapMetricsUseCase:
    """Calculate transparent gap signals without semantic inference.

    ``target_coverage`` is the fraction of cohort jobs requiring the capability.
    ``must_have_ratio`` is the fraction of that capability's requirements marked
    must-have. ``evidence_coverage`` is strict: 1.0 only when explicit Profile
    Evidence exists, otherwise 0.0. It never assigns partial evidence that the user
    did not provide.

    ``gap_severity`` combines demand breadth, requirement importance, and the
    already-explicit coverage state. Missing skills use deficit weight 1.0;
    explicit-but-unevidenced skills use 0.5; evidenced skills use 0.0::

        target_coverage * (0.5 + 0.5 * must_have_ratio) * deficit_weight

    The result is a ranking signal only; it is not a probability or quality gate.
    """

    def execute(
        self,
        comparison: TargetCohortProfileComparisonResult,
    ) -> TargetCohortSkillGapMetricsResult:
        if not comparison.facts_usable:
            return self._blocked(comparison)
        if not comparison.job_ids:
            return self._blocked(comparison, "empty_target_cohort")

        cohort_size = len(comparison.job_ids)
        items: list[TargetCohortSkillGapMetric] = []
        for capability in comparison.capabilities:
            if capability.requirement_count <= 0:
                return self._blocked(comparison, "invalid_requirement_count")

            target_coverage = capability.job_count / cohort_size
            must_have_ratio = capability.must_have_count / capability.requirement_count
            evidence_coverage = _EVIDENCE_COVERAGE[capability.status]
            importance_weight = 0.5 + (0.5 * must_have_ratio)
            deficit_weight = _GAP_DEFICIT_WEIGHT[capability.status]
            gap_severity = target_coverage * importance_weight * deficit_weight

            items.append(
                TargetCohortSkillGapMetric(
                    capability=capability.capability,
                    coverage_status=capability.status,
                    target_coverage=round(target_coverage, 6),
                    must_have_ratio=round(must_have_ratio, 6),
                    evidence_coverage=evidence_coverage,
                    gap_severity=round(gap_severity, 6),
                    supporting_requirement_ids=capability.requirement_ids,
                    supporting_job_ids=capability.job_ids,
                    profile_skill_ids=capability.profile_skill_ids,
                    evidence_ids=capability.evidence_ids,
                )
            )

        return TargetCohortSkillGapMetricsResult(
            cohort_id=comparison.cohort_id,
            job_ids=comparison.job_ids,
            facts_usable=True,
            profile_id=comparison.profile_id,
            profile_version=comparison.profile_version,
            items=tuple(items),
        )

    @staticmethod
    def _blocked(
        comparison: TargetCohortProfileComparisonResult,
        blocker: str | None = None,
    ) -> TargetCohortSkillGapMetricsResult:
        return TargetCohortSkillGapMetricsResult(
            cohort_id=comparison.cohort_id,
            job_ids=comparison.job_ids,
            facts_usable=False,
            profile_id=comparison.profile_id,
            profile_version=comparison.profile_version,
            items=(),
            blockers=() if blocker is None else (blocker,),
        )


__all__ = [
    "CalculateTargetCohortSkillGapMetricsUseCase",
    "TargetCohortSkillGapMetric",
    "TargetCohortSkillGapMetricsResult",
]

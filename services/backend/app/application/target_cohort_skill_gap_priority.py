"""Deterministic P0/P1 priority contract for TargetCohort SkillGap metrics."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.application.target_cohort_profile_comparison import ProfileCapabilityCoverageStatus
from app.application.target_cohort_skill_gap_metrics import TargetCohortSkillGapMetricsResult


class SkillGapPriority(StrEnum):
    P0 = "P0"
    P1 = "P1"


@dataclass(frozen=True, slots=True)
class PrioritizedTargetCohortSkillGap:
    capability: str
    priority: SkillGapPriority
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
class PrioritizeTargetCohortSkillGapsResult:
    cohort_id: str
    job_ids: tuple[str, ...]
    facts_usable: bool
    profile_id: str | None
    profile_version: int | None
    items: tuple[PrioritizedTargetCohortSkillGap, ...]
    blockers: tuple[str, ...] = ()
    db_writes: int = 0
    provider_calls: int = 0
    trace_runs_created: int = 0


class PrioritizeTargetCohortSkillGapsUseCase:
    """Turn transparent gap metrics into a stable P0/P1 backlog.

    P0 is reserved for gaps whose existing ``gap_severity`` is at least 0.5.
    That signal already combines target-job coverage, must-have importance, and the
    user's explicit evidence deficit, so priority is not based on market frequency
    alone. Remaining real gaps are P1. Fully evidenced capabilities are not gaps and
    are omitted.

    This layer deliberately does not generate actions or completion criteria.
    """

    P0_GAP_SEVERITY_THRESHOLD = 0.5

    def execute(
        self,
        metrics: TargetCohortSkillGapMetricsResult,
    ) -> PrioritizeTargetCohortSkillGapsResult:
        if not metrics.facts_usable:
            return self._blocked(metrics)

        items: list[PrioritizedTargetCohortSkillGap] = []
        for metric in metrics.items:
            if metric.coverage_status is ProfileCapabilityCoverageStatus.EVIDENCED:
                continue
            if metric.gap_severity <= 0:
                continue

            priority = (
                SkillGapPriority.P0
                if metric.gap_severity >= self.P0_GAP_SEVERITY_THRESHOLD
                else SkillGapPriority.P1
            )
            items.append(
                PrioritizedTargetCohortSkillGap(
                    capability=metric.capability,
                    priority=priority,
                    coverage_status=metric.coverage_status,
                    target_coverage=metric.target_coverage,
                    must_have_ratio=metric.must_have_ratio,
                    evidence_coverage=metric.evidence_coverage,
                    gap_severity=metric.gap_severity,
                    supporting_requirement_ids=metric.supporting_requirement_ids,
                    supporting_job_ids=metric.supporting_job_ids,
                    profile_skill_ids=metric.profile_skill_ids,
                    evidence_ids=metric.evidence_ids,
                )
            )

        items.sort(
            key=lambda item: (
                -item.gap_severity,
                -item.target_coverage,
                item.capability.casefold(),
                item.capability,
            )
        )

        return PrioritizeTargetCohortSkillGapsResult(
            cohort_id=metrics.cohort_id,
            job_ids=metrics.job_ids,
            facts_usable=True,
            profile_id=metrics.profile_id,
            profile_version=metrics.profile_version,
            items=tuple(items),
        )

    @staticmethod
    def _blocked(
        metrics: TargetCohortSkillGapMetricsResult,
    ) -> PrioritizeTargetCohortSkillGapsResult:
        return PrioritizeTargetCohortSkillGapsResult(
            cohort_id=metrics.cohort_id,
            job_ids=metrics.job_ids,
            facts_usable=False,
            profile_id=metrics.profile_id,
            profile_version=metrics.profile_version,
            items=(),
            blockers=metrics.blockers,
        )


__all__ = [
    "PrioritizeTargetCohortSkillGapsResult",
    "PrioritizeTargetCohortSkillGapsUseCase",
    "PrioritizedTargetCohortSkillGap",
    "SkillGapPriority",
]

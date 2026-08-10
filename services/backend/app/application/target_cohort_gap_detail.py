"""Read-only Phase 6 acceptance projection for TargetCohort SkillGaps."""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from app.application.target_cohort_action_plan import BuildTargetCohortActionPlanResult
from app.application.target_cohort_skill_gap_priority import SkillGapPriority


@dataclass(frozen=True, slots=True)
class TargetCohortGapDetail:
    capability: str
    priority: SkillGapPriority
    why_important: Mapping[str, float]
    supporting_requirement_ids: tuple[str, ...]
    supporting_job_ids: tuple[str, ...]
    profile_skill_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    current_state: str
    completion_criteria: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BuildTargetCohortGapDetailsResult:
    cohort_id: str
    job_ids: tuple[str, ...]
    facts_usable: bool
    profile_id: str | None
    profile_version: int | None
    items: tuple[TargetCohortGapDetail, ...]
    blockers: tuple[str, ...] = ()
    db_writes: int = 0
    provider_calls: int = 0
    trace_runs_created: int = 0


class BuildTargetCohortGapDetailsUseCase:
    """Project grounded Action Plan facts into the Phase 6 acceptance view.

    This use case adds no new career claims or learning recommendations. It only
    reorganizes already-grounded market/Profile provenance so a caller can show
    why a gap matters, which jobs/requirements support it, what Profile facts
    exist, what is missing, and what confirmed state would close the gap.
    """

    def execute(
        self,
        plan: BuildTargetCohortActionPlanResult,
    ) -> BuildTargetCohortGapDetailsResult:
        if not plan.facts_usable:
            return BuildTargetCohortGapDetailsResult(
                cohort_id=plan.cohort_id,
                job_ids=plan.job_ids,
                facts_usable=False,
                profile_id=plan.profile_id,
                profile_version=plan.profile_version,
                items=(),
                blockers=plan.blockers,
            )

        items = tuple(
            TargetCohortGapDetail(
                capability=item.capability,
                priority=item.priority,
                why_important=MappingProxyType(
                    {
                        "targetCoverage": item.target_coverage,
                        "mustHaveRatio": item.must_have_ratio,
                        "gapSeverity": item.gap_severity,
                    }
                ),
                supporting_requirement_ids=item.supporting_requirement_ids,
                supporting_job_ids=item.supporting_job_ids,
                profile_skill_ids=item.profile_skill_ids,
                evidence_ids=item.evidence_ids,
                current_state=item.current_state,
                completion_criteria=item.completion_criteria,
            )
            for item in plan.items
        )

        return BuildTargetCohortGapDetailsResult(
            cohort_id=plan.cohort_id,
            job_ids=plan.job_ids,
            facts_usable=True,
            profile_id=plan.profile_id,
            profile_version=plan.profile_version,
            items=items,
        )


__all__ = [
    "BuildTargetCohortGapDetailsResult",
    "BuildTargetCohortGapDetailsUseCase",
    "TargetCohortGapDetail",
]

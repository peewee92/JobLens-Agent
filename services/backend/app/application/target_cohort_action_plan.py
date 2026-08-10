"""Deterministic minimal Action Plan contract for prioritized TargetCohort SkillGaps."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.application.target_cohort_profile_comparison import ProfileCapabilityCoverageStatus
from app.application.target_cohort_skill_gap_priority import (
    PrioritizeTargetCohortSkillGapsResult,
    SkillGapPriority,
)


class SkillGapActionKind(StrEnum):
    BUILD_CAPABILITY_AND_EVIDENCE = "build_capability_and_evidence"
    ADD_EVIDENCE = "add_evidence"


@dataclass(frozen=True, slots=True)
class TargetCohortActionPlanItem:
    capability: str
    priority: SkillGapPriority
    action_kind: SkillGapActionKind
    current_state: str
    completion_criteria: tuple[str, ...]
    target_coverage: float
    must_have_ratio: float
    evidence_coverage: float
    gap_severity: float
    supporting_requirement_ids: tuple[str, ...]
    supporting_job_ids: tuple[str, ...]
    profile_skill_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BuildTargetCohortActionPlanResult:
    cohort_id: str
    job_ids: tuple[str, ...]
    facts_usable: bool
    profile_id: str | None
    profile_version: int | None
    items: tuple[TargetCohortActionPlanItem, ...]
    blockers: tuple[str, ...] = ()
    db_writes: int = 0
    provider_calls: int = 0
    trace_runs_created: int = 0


class BuildTargetCohortActionPlanUseCase:
    """Turn prioritized gaps into grounded, completion-oriented action items.

    The plan is intentionally narrow: it states what fact is missing and what
    confirmed Profile state would count as closing that gap. It does not invent
    courses, projects, timelines, or user experience.
    """

    def execute(
        self,
        prioritized: PrioritizeTargetCohortSkillGapsResult,
    ) -> BuildTargetCohortActionPlanResult:
        if not prioritized.facts_usable:
            return BuildTargetCohortActionPlanResult(
                cohort_id=prioritized.cohort_id,
                job_ids=prioritized.job_ids,
                facts_usable=False,
                profile_id=prioritized.profile_id,
                profile_version=prioritized.profile_version,
                items=(),
                blockers=prioritized.blockers,
            )

        items: list[TargetCohortActionPlanItem] = []
        for gap in prioritized.items:
            if gap.coverage_status is ProfileCapabilityCoverageStatus.MISSING:
                action_kind = SkillGapActionKind.BUILD_CAPABILITY_AND_EVIDENCE
                current_state = "capability_missing"
                completion_criteria = (
                    "confirmed_profile_skill_exists",
                    "confirmed_evidence_linked_to_skill_exists",
                )
            elif gap.coverage_status is ProfileCapabilityCoverageStatus.UNEVIDENCED:
                action_kind = SkillGapActionKind.ADD_EVIDENCE
                current_state = "skill_exists_without_confirmed_evidence"
                completion_criteria = ("confirmed_evidence_linked_to_skill_exists",)
            else:
                continue

            items.append(
                TargetCohortActionPlanItem(
                    capability=gap.capability,
                    priority=gap.priority,
                    action_kind=action_kind,
                    current_state=current_state,
                    completion_criteria=completion_criteria,
                    target_coverage=gap.target_coverage,
                    must_have_ratio=gap.must_have_ratio,
                    evidence_coverage=gap.evidence_coverage,
                    gap_severity=gap.gap_severity,
                    supporting_requirement_ids=gap.supporting_requirement_ids,
                    supporting_job_ids=gap.supporting_job_ids,
                    profile_skill_ids=gap.profile_skill_ids,
                    evidence_ids=gap.evidence_ids,
                )
            )

        return BuildTargetCohortActionPlanResult(
            cohort_id=prioritized.cohort_id,
            job_ids=prioritized.job_ids,
            facts_usable=True,
            profile_id=prioritized.profile_id,
            profile_version=prioritized.profile_version,
            items=tuple(items),
        )


__all__ = [
    "BuildTargetCohortActionPlanResult",
    "BuildTargetCohortActionPlanUseCase",
    "SkillGapActionKind",
    "TargetCohortActionPlanItem",
]

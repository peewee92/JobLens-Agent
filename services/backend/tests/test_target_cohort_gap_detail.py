"""Read-only acceptance projection for a single TargetCohort SkillGap."""
from __future__ import annotations

from app.application.target_cohort_action_plan import (
    BuildTargetCohortActionPlanResult,
    SkillGapActionKind,
    TargetCohortActionPlanItem,
)
from app.application.target_cohort_gap_detail import BuildTargetCohortGapDetailsUseCase
from app.application.target_cohort_skill_gap_priority import SkillGapPriority


def _plan(*items: TargetCohortActionPlanItem) -> BuildTargetCohortActionPlanResult:
    return BuildTargetCohortActionPlanResult(
        cohort_id="cohort_1",
        job_ids=("job_1", "job_2"),
        facts_usable=True,
        profile_id="profile_1",
        profile_version=3,
        items=items,
    )


def _item() -> TargetCohortActionPlanItem:
    return TargetCohortActionPlanItem(
        capability="Kafka",
        priority=SkillGapPriority.P0,
        action_kind=SkillGapActionKind.BUILD_CAPABILITY_AND_EVIDENCE,
        current_state="capability_missing",
        completion_criteria=(
            "confirmed_profile_skill_exists",
            "confirmed_evidence_linked_to_skill_exists",
        ),
        target_coverage=1.0,
        must_have_ratio=0.5,
        evidence_coverage=0.0,
        gap_severity=0.75,
        supporting_requirement_ids=("req_1", "req_2"),
        supporting_job_ids=("job_1", "job_2"),
        profile_skill_ids=(),
        evidence_ids=(),
    )


def test_gap_detail_exposes_every_phase_6_acceptance_fact_without_invention() -> None:
    result = BuildTargetCohortGapDetailsUseCase().execute(_plan(_item()))

    assert result.facts_usable is True
    assert len(result.items) == 1
    detail = result.items[0]
    assert detail.capability == "Kafka"
    assert detail.priority is SkillGapPriority.P0
    assert detail.why_important == {
        "targetCoverage": 1.0,
        "mustHaveRatio": 0.5,
        "gapSeverity": 0.75,
    }
    assert detail.supporting_requirement_ids == ("req_1", "req_2")
    assert detail.supporting_job_ids == ("job_1", "job_2")
    assert detail.profile_skill_ids == ()
    assert detail.evidence_ids == ()
    assert detail.current_state == "capability_missing"
    assert detail.completion_criteria == (
        "confirmed_profile_skill_exists",
        "confirmed_evidence_linked_to_skill_exists",
    )
    assert not hasattr(detail, "course")
    assert not hasattr(detail, "estimated_hours")
    assert result.db_writes == 0
    assert result.provider_calls == 0
    assert result.trace_runs_created == 0


def test_gap_detail_preserves_existing_evidence_provenance() -> None:
    item = TargetCohortActionPlanItem(
        capability="FastAPI",
        priority=SkillGapPriority.P1,
        action_kind=SkillGapActionKind.ADD_EVIDENCE,
        current_state="skill_exists_without_confirmed_evidence",
        completion_criteria=("confirmed_evidence_linked_to_skill_exists",),
        target_coverage=0.5,
        must_have_ratio=1.0,
        evidence_coverage=0.0,
        gap_severity=0.4,
        supporting_requirement_ids=("req_fastapi",),
        supporting_job_ids=("job_2",),
        profile_skill_ids=("skill_fastapi",),
        evidence_ids=(),
    )

    detail = BuildTargetCohortGapDetailsUseCase().execute(_plan(item)).items[0]

    assert detail.profile_skill_ids == ("skill_fastapi",)
    assert detail.evidence_ids == ()
    assert detail.current_state == "skill_exists_without_confirmed_evidence"


def test_gap_detail_fails_closed_when_action_plan_facts_are_unusable() -> None:
    plan = BuildTargetCohortActionPlanResult(
        cohort_id="cohort_blocked",
        job_ids=("job_1",),
        facts_usable=False,
        profile_id="profile_1",
        profile_version=3,
        items=(),
        blockers=("requirements_not_released",),
    )

    result = BuildTargetCohortGapDetailsUseCase().execute(plan)

    assert result.facts_usable is False
    assert result.items == ()
    assert result.blockers == ("requirements_not_released",)
    assert result.db_writes == 0
    assert result.provider_calls == 0
    assert result.trace_runs_created == 0

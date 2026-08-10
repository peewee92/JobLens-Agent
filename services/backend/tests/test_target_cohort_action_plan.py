"""Deterministic minimal Action Plan contract for prioritized TargetCohort SkillGaps."""
from __future__ import annotations

from app.application.target_cohort_action_plan import (
    BuildTargetCohortActionPlanUseCase,
    SkillGapActionKind,
)
from app.application.target_cohort_profile_comparison import ProfileCapabilityCoverageStatus
from app.application.target_cohort_skill_gap_priority import (
    PrioritizeTargetCohortSkillGapsResult,
    PrioritizedTargetCohortSkillGap,
    SkillGapPriority,
)


def _gap(
    capability: str,
    *,
    priority: SkillGapPriority,
    status: ProfileCapabilityCoverageStatus,
    target_coverage: float,
    must_have_ratio: float,
    profile_skill_ids: tuple[str, ...] = (),
) -> PrioritizedTargetCohortSkillGap:
    return PrioritizedTargetCohortSkillGap(
        capability=capability,
        priority=priority,
        coverage_status=status,
        target_coverage=target_coverage,
        must_have_ratio=must_have_ratio,
        evidence_coverage=0.0,
        gap_severity=0.7 if priority is SkillGapPriority.P0 else 0.3,
        supporting_requirement_ids=(f"req_{capability}_1", f"req_{capability}_2"),
        supporting_job_ids=(f"job_{capability}_1", f"job_{capability}_2"),
        profile_skill_ids=profile_skill_ids,
        evidence_ids=(),
    )


def _prioritized(*items: PrioritizedTargetCohortSkillGap) -> PrioritizeTargetCohortSkillGapsResult:
    return PrioritizeTargetCohortSkillGapsResult(
        cohort_id="cohort_1",
        job_ids=("job_1", "job_2", "job_3", "job_4"),
        facts_usable=True,
        profile_id="profile_1",
        profile_version=3,
        items=items,
    )


def test_action_plan_distinguishes_missing_capability_from_missing_evidence() -> None:
    result = BuildTargetCohortActionPlanUseCase().execute(
        _prioritized(
            _gap(
                "Kafka",
                priority=SkillGapPriority.P0,
                status=ProfileCapabilityCoverageStatus.MISSING,
                target_coverage=0.75,
                must_have_ratio=1.0,
            ),
            _gap(
                "FastAPI",
                priority=SkillGapPriority.P1,
                status=ProfileCapabilityCoverageStatus.UNEVIDENCED,
                target_coverage=0.5,
                must_have_ratio=0.5,
                profile_skill_ids=("skill_fastapi",),
            ),
        )
    )

    assert result.facts_usable is True
    assert [item.capability for item in result.items] == ["Kafka", "FastAPI"]

    missing, unevidenced = result.items
    assert missing.action_kind is SkillGapActionKind.BUILD_CAPABILITY_AND_EVIDENCE
    assert missing.current_state == "capability_missing"
    assert missing.completion_criteria == (
        "confirmed_profile_skill_exists",
        "confirmed_evidence_linked_to_skill_exists",
    )
    assert missing.supporting_requirement_ids == ("req_Kafka_1", "req_Kafka_2")
    assert missing.supporting_job_ids == ("job_Kafka_1", "job_Kafka_2")

    assert unevidenced.action_kind is SkillGapActionKind.ADD_EVIDENCE
    assert unevidenced.current_state == "skill_exists_without_confirmed_evidence"
    assert unevidenced.completion_criteria == ("confirmed_evidence_linked_to_skill_exists",)
    assert unevidenced.profile_skill_ids == ("skill_fastapi",)
    assert result.db_writes == 0
    assert result.provider_calls == 0
    assert result.trace_runs_created == 0


def test_action_plan_preserves_priority_and_market_facts_without_inventing_learning_steps() -> None:
    result = BuildTargetCohortActionPlanUseCase().execute(
        _prioritized(
            _gap(
                "Kafka",
                priority=SkillGapPriority.P0,
                status=ProfileCapabilityCoverageStatus.MISSING,
                target_coverage=0.75,
                must_have_ratio=2 / 3,
            )
        )
    )

    item = result.items[0]
    assert item.priority is SkillGapPriority.P0
    assert item.target_coverage == 0.75
    assert item.must_have_ratio == 2 / 3
    assert item.gap_severity == 0.7
    assert not hasattr(item, "course")
    assert not hasattr(item, "project")
    assert not hasattr(item, "estimated_hours")


def test_action_plan_fails_closed_when_prioritized_facts_are_unusable() -> None:
    prioritized = PrioritizeTargetCohortSkillGapsResult(
        cohort_id="cohort_blocked",
        job_ids=("job_1",),
        facts_usable=False,
        profile_id="profile_1",
        profile_version=3,
        items=(),
        blockers=("requirements_not_released",),
    )

    result = BuildTargetCohortActionPlanUseCase().execute(prioritized)

    assert result.facts_usable is False
    assert result.items == ()
    assert result.blockers == ("requirements_not_released",)
    assert result.db_writes == 0
    assert result.provider_calls == 0
    assert result.trace_runs_created == 0

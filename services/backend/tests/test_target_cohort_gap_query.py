from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from app.application.career_context.models import EvidenceDetail, ProfileDetail, SkillDetail
from app.application.create_target_cohort import CreateFeedbackTargetCohortCommand
from app.application.target_cohort_gap_query import BuildSelectedFeedbackTargetCohortGapDetailsUseCase
from app.application.target_cohort_requirement_aggregation import TargetCohortRequirementAggregationResult
from app.domain.career_context import EvidenceType, SkillLevel
from app.domain.target_cohort import TargetCohortSelectionSource, TargetCohortSnapshot


class _Creator:
    def execute(self, command: CreateFeedbackTargetCohortCommand):
        assert command.selected_feedback_ids == ("feedback_1",)
        return SimpleNamespace(
            cohort=TargetCohortSnapshot.create(
                cohort_id=command.cohort_id,
                name=command.name,
                selection_source=TargetCohortSelectionSource.MANUAL,
                job_ids=("job_1",),
            )
        )


class _Aggregator:
    def __init__(self, *, usable: bool = True) -> None:
        self.usable = usable

    def execute(self, cohort: TargetCohortSnapshot):
        blockers = ()
        if not self.usable:
            blockers = (SimpleNamespace(job_id="job_1", codes=("human_baseline_missing",)),)
        return TargetCohortRequirementAggregationResult(
            cohort_id=cohort.id,
            job_ids=cohort.job_ids,
            facts_usable=self.usable,
            sources=(),
            requirements=(),
            blockers=blockers,
        )


class _Profiles:
    def __init__(self, profile: ProfileDetail | None) -> None:
        self.profile = profile

    def get_current_profile(self) -> ProfileDetail | None:
        return self.profile


def _profile() -> ProfileDetail:
    return ProfileDetail(
        id="profile_1",
        version=3,
        created_at=datetime(2026, 8, 10, tzinfo=timezone.utc),
        headline="Frontend engineer",
        years_of_experience=8,
        evidence=(
            EvidenceDetail(
                id="evidence_1",
                key="react-project",
                type=EvidenceType.PROJECT,
                summary="Built React applications",
                source="confirmed resume",
            ),
        ),
        skills=(
            SkillDetail(
                id="skill_1",
                name="React",
                level=SkillLevel.STRONG,
                evidence_ids=("evidence_1",),
            ),
        ),
    )


def _use_case(*, profile: ProfileDetail | None = None, usable: bool = True):
    return BuildSelectedFeedbackTargetCohortGapDetailsUseCase(
        cohort_creator=_Creator(),
        requirement_aggregator=_Aggregator(usable=usable),
        profiles=_Profiles(profile if profile is not None else _profile()),
    )


def test_gap_query_composes_existing_deterministic_pipeline() -> None:
    result = _use_case().execute(
        CreateFeedbackTargetCohortCommand(
            cohort_id="cohort_1",
            name="AI frontend targets",
            selected_feedback_ids=("feedback_1",),
        )
    )

    assert result.cohort_id == "cohort_1"
    assert result.job_ids == ("job_1",)
    assert result.facts_usable is True
    assert result.profile_id == "profile_1"
    assert result.profile_version == 3
    assert result.items == ()
    assert result.blockers == ()
    assert result.db_writes == 0
    assert result.provider_calls == 0
    assert result.trace_runs_created == 0


def test_gap_query_fails_closed_when_requirement_facts_are_not_released() -> None:
    result = _use_case(usable=False).execute(
        CreateFeedbackTargetCohortCommand(
            cohort_id="cohort_1",
            name="AI frontend targets",
            selected_feedback_ids=("feedback_1",),
        )
    )

    assert result.facts_usable is False
    assert result.items == ()
    assert result.blockers == ("job_1:human_baseline_missing",)


def test_gap_query_fails_closed_without_confirmed_profile() -> None:
    use_case = BuildSelectedFeedbackTargetCohortGapDetailsUseCase(
        cohort_creator=_Creator(),
        requirement_aggregator=_Aggregator(),
        profiles=_Profiles(None),
    )
    result = use_case.execute(
        CreateFeedbackTargetCohortCommand(
            cohort_id="cohort_1",
            name="AI frontend targets",
            selected_feedback_ids=("feedback_1",),
        )
    )

    assert result.facts_usable is False
    assert result.profile_id is None
    assert result.items == ()
    assert result.blockers == ("profile_missing",)

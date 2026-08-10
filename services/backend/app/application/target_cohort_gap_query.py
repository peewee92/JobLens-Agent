"""Read-only orchestration from an explicit feedback cohort to Gap Detail facts."""
from __future__ import annotations

from typing import Protocol

from app.application.create_target_cohort import (
    CreateFeedbackTargetCohortCommand,
    CreateFeedbackTargetCohortResult,
)
from app.application.ports.career_context_repository import AbstractCareerContextQueryRepository
from app.application.target_cohort_action_plan import BuildTargetCohortActionPlanUseCase
from app.application.target_cohort_capability_normalization import NormalizeTargetCohortCapabilitiesUseCase
from app.application.target_cohort_gap_detail import (
    BuildTargetCohortGapDetailsResult,
    BuildTargetCohortGapDetailsUseCase,
)
from app.application.target_cohort_profile_comparison import CompareTargetCohortCapabilitiesToProfileUseCase
from app.application.target_cohort_requirement_aggregation import (
    TargetCohortRequirementAggregationResult,
)
from app.application.target_cohort_skill_gap_metrics import CalculateTargetCohortSkillGapMetricsUseCase
from app.application.target_cohort_skill_gap_priority import PrioritizeTargetCohortSkillGapsUseCase
from app.domain.target_cohort import TargetCohortSnapshot


class FeedbackTargetCohortCreator(Protocol):
    def execute(
        self,
        command: CreateFeedbackTargetCohortCommand,
    ) -> CreateFeedbackTargetCohortResult: ...


class TargetCohortRequirementAggregator(Protocol):
    def execute(
        self,
        cohort: TargetCohortSnapshot,
    ) -> TargetCohortRequirementAggregationResult: ...


class BuildSelectedFeedbackTargetCohortGapDetailsUseCase:
    """Compose the existing deterministic Phase 6 pipeline without side effects.

    Cohort membership remains an explicit user selection of current feedback records.
    Requirement facts must pass their existing release gate before they reach this use
    case, and Profile facts come only from the latest confirmed Profile repository.
    No Provider, Trace, persistence, fuzzy matching, or career-evidence inference is
    introduced here.
    """

    def __init__(
        self,
        *,
        cohort_creator: FeedbackTargetCohortCreator,
        requirement_aggregator: TargetCohortRequirementAggregator,
        profiles: AbstractCareerContextQueryRepository,
    ) -> None:
        self._cohort_creator = cohort_creator
        self._requirement_aggregator = requirement_aggregator
        self._profiles = profiles
        self._normalizer = NormalizeTargetCohortCapabilitiesUseCase()
        self._comparer = CompareTargetCohortCapabilitiesToProfileUseCase()
        self._metrics = CalculateTargetCohortSkillGapMetricsUseCase()
        self._prioritizer = PrioritizeTargetCohortSkillGapsUseCase()
        self._action_plan = BuildTargetCohortActionPlanUseCase()
        self._details = BuildTargetCohortGapDetailsUseCase()

    def execute(
        self,
        command: CreateFeedbackTargetCohortCommand,
    ) -> BuildTargetCohortGapDetailsResult:
        cohort_result = self._cohort_creator.execute(command)
        cohort = cohort_result.cohort
        aggregation = self._requirement_aggregator.execute(cohort)
        if not aggregation.facts_usable:
            blockers = tuple(
                f"{blocker.job_id}:{code}"
                for blocker in aggregation.blockers
                for code in blocker.codes
            )
            return BuildTargetCohortGapDetailsResult(
                cohort_id=cohort.id,
                job_ids=cohort.job_ids,
                facts_usable=False,
                profile_id=None,
                profile_version=None,
                items=(),
                blockers=blockers,
            )

        profile = self._profiles.get_current_profile()
        if profile is None:
            return BuildTargetCohortGapDetailsResult(
                cohort_id=cohort.id,
                job_ids=cohort.job_ids,
                facts_usable=False,
                profile_id=None,
                profile_version=None,
                items=(),
                blockers=("profile_missing",),
            )

        market = self._normalizer.execute(aggregation)
        comparison = self._comparer.execute(market, profile)
        metrics = self._metrics.execute(comparison)
        prioritized = self._prioritizer.execute(metrics)
        plan = self._action_plan.execute(prioritized)
        return self._details.execute(plan)


__all__ = ["BuildSelectedFeedbackTargetCohortGapDetailsUseCase"]

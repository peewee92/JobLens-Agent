"""Create a transient TargetCohort only from explicit, current user selections."""
from dataclasses import dataclass

import pytest

from app.application.create_target_cohort import (
    CreateFeedbackTargetCohortCommand,
    CreateFeedbackTargetCohortUseCase,
    TargetCohortSelectionError,
)
from app.application.user_feedback_target_cohort import (
    UserFeedbackTargetCohortCandidate,
    UserFeedbackTargetCohortSourceResult,
)
from app.domain.target_cohort import TargetCohortSelectionSource
from app.domain.user_feedback import FeedbackDecision


@dataclass
class _Source:
    result: UserFeedbackTargetCohortSourceResult
    calls: int = 0

    def execute(self) -> UserFeedbackTargetCohortSourceResult:
        self.calls += 1
        return self.result


def _source_result() -> UserFeedbackTargetCohortSourceResult:
    return UserFeedbackTargetCohortSourceResult(
        candidates=(
            UserFeedbackTargetCohortCandidate(
                job_id="job_1",
                feedback_id="feedback_1",
                match_report_id="report_1",
                decision=FeedbackDecision.INTERESTED,
            ),
            UserFeedbackTargetCohortCandidate(
                job_id="job_2",
                feedback_id="feedback_2",
                match_report_id="report_2",
                decision=FeedbackDecision.MAYBE,
            ),
        ),
        total_feedback_records=3,
        latest_job_feedback_count=3,
        excluded_rejected_job_ids=("job_3",),
    )


def test_creates_feedback_cohort_only_from_explicit_selected_feedback_ids() -> None:
    source = _Source(_source_result())

    result = CreateFeedbackTargetCohortUseCase(source=source).execute(
        CreateFeedbackTargetCohortCommand(
            cohort_id="cohort_1",
            name="Frontend AI targets",
            selected_feedback_ids=("feedback_2", "feedback_1", "feedback_2"),
        )
    )

    assert result.cohort.id == "cohort_1"
    assert result.cohort.name == "Frontend AI targets"
    assert result.cohort.selection_source is TargetCohortSelectionSource.USER_FEEDBACK
    assert result.cohort.job_ids == ("job_2", "job_1")
    assert result.cohort.sample_size == 2
    assert [item.feedback_id for item in result.cohort.created_from_feedback] == [
        "feedback_2",
        "feedback_1",
    ]
    assert result.db_writes == 0
    assert result.provider_calls == 0
    assert result.trace_runs_created == 0
    assert source.calls == 1


def test_maybe_candidate_is_not_auto_selected() -> None:
    source = _Source(_source_result())

    result = CreateFeedbackTargetCohortUseCase(source=source).execute(
        CreateFeedbackTargetCohortCommand(
            cohort_id="cohort_1",
            name="Explicit choice",
            selected_feedback_ids=("feedback_1",),
        )
    )

    assert result.cohort.job_ids == ("job_1",)
    assert [item.feedback_id for item in result.cohort.created_from_feedback] == ["feedback_1"]


def test_rejects_blank_or_stale_feedback_selection_instead_of_guessing_by_job() -> None:
    source = _Source(_source_result())
    use_case = CreateFeedbackTargetCohortUseCase(source=source)

    with pytest.raises(TargetCohortSelectionError, match="at least one"):
        use_case.execute(
            CreateFeedbackTargetCohortCommand(
                cohort_id="cohort_1",
                name="Empty",
                selected_feedback_ids=(),
            )
        )

    with pytest.raises(TargetCohortSelectionError, match="not a current cohort candidate"):
        use_case.execute(
            CreateFeedbackTargetCohortCommand(
                cohort_id="cohort_2",
                name="Stale",
                selected_feedback_ids=("old_feedback",),
            )
        )

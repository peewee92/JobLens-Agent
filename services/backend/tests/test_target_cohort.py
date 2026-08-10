"""TargetCohort domain contract for explicit v0.2 cohort creation."""
from __future__ import annotations

import pytest

from app.domain.target_cohort import (
    TargetCohortFeedbackSource,
    TargetCohortSelectionSource,
    TargetCohortSnapshot,
)


def test_feedback_target_cohort_is_immutable_traceable_and_deduplicated() -> None:
    cohort = TargetCohortSnapshot.create(
        cohort_id=" cohort_1 ",
        name=" AI Agent roles ",
        selection_source=TargetCohortSelectionSource.USER_FEEDBACK,
        job_ids=("job_2", "job_1", "job_2"),
        created_from_feedback=(
            TargetCohortFeedbackSource(
                feedback_id="feedback_2",
                match_report_id="report_2",
                job_id="job_2",
            ),
            TargetCohortFeedbackSource(
                feedback_id="feedback_1",
                match_report_id="report_1",
                job_id="job_1",
            ),
        ),
    )

    assert cohort.id == "cohort_1"
    assert cohort.name == "AI Agent roles"
    assert cohort.selection_source is TargetCohortSelectionSource.USER_FEEDBACK
    assert cohort.job_ids == ("job_2", "job_1")
    assert cohort.sample_size == 2
    assert [item.feedback_id for item in cohort.created_from_feedback] == [
        "feedback_2",
        "feedback_1",
    ]


def test_feedback_target_cohort_requires_exact_feedback_provenance_for_each_job() -> None:
    with pytest.raises(ValueError, match="feedback provenance must cover cohort job_ids exactly"):
        TargetCohortSnapshot.create(
            cohort_id="cohort_1",
            name="Agent roles",
            selection_source=TargetCohortSelectionSource.USER_FEEDBACK,
            job_ids=("job_1", "job_2"),
            created_from_feedback=(
                TargetCohortFeedbackSource(
                    feedback_id="feedback_1",
                    match_report_id="report_1",
                    job_id="job_1",
                ),
            ),
        )


def test_feedback_target_cohort_rejects_duplicate_or_foreign_feedback_provenance() -> None:
    with pytest.raises(ValueError, match="feedback provenance must contain one item per job"):
        TargetCohortSnapshot.create(
            cohort_id="cohort_1",
            name="Agent roles",
            selection_source=TargetCohortSelectionSource.USER_FEEDBACK,
            job_ids=("job_1",),
            created_from_feedback=(
                TargetCohortFeedbackSource("feedback_1", "report_1", "job_1"),
                TargetCohortFeedbackSource("feedback_2", "report_2", "job_1"),
            ),
        )


def test_manual_target_cohort_cannot_claim_feedback_provenance() -> None:
    with pytest.raises(ValueError, match="manual cohort must not claim feedback provenance"):
        TargetCohortSnapshot.create(
            cohort_id="cohort_1",
            name="Hand picked roles",
            selection_source=TargetCohortSelectionSource.MANUAL,
            job_ids=("job_1",),
            created_from_feedback=(
                TargetCohortFeedbackSource("feedback_1", "report_1", "job_1"),
            ),
        )


def test_target_cohort_requires_non_blank_identity_name_and_jobs() -> None:
    with pytest.raises(ValueError, match="cohort_id must not be blank"):
        TargetCohortSnapshot.create(
            cohort_id=" ",
            name="Agent roles",
            selection_source=TargetCohortSelectionSource.MANUAL,
            job_ids=("job_1",),
        )

    with pytest.raises(ValueError, match="name must not be blank"):
        TargetCohortSnapshot.create(
            cohort_id="cohort_1",
            name=" ",
            selection_source=TargetCohortSelectionSource.MANUAL,
            job_ids=("job_1",),
        )

    with pytest.raises(ValueError, match="job_ids must not be empty"):
        TargetCohortSnapshot.create(
            cohort_id="cohort_1",
            name="Agent roles",
            selection_source=TargetCohortSelectionSource.MANUAL,
            job_ids=(),
        )

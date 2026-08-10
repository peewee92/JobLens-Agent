"""Deterministic UserFeedback source candidates for a future Target Cohort."""
from datetime import UTC, datetime, timedelta

import pytest

from app.application.user_feedback import UserFeedbackPersistenceNotReadyError
from app.application.user_feedback_persistence import UserFeedbackPersistenceReadiness
from app.application.user_feedback_target_cohort import UserFeedbackTargetCohortSourceUseCase
from app.domain.user_feedback import FeedbackDecision, FeedbackReason, StoredUserFeedback, UserFeedbackDraft


NOW = datetime(2026, 8, 10, tzinfo=UTC)


def _feedback(
    feedback_id: str,
    *,
    job_id: str,
    report_id: str,
    decision: FeedbackDecision,
    created_at: datetime,
) -> StoredUserFeedback:
    reasons = (FeedbackReason.ROLE_FIT,) if decision is FeedbackDecision.REJECTED else ()
    return StoredUserFeedback(
        id=feedback_id,
        feedback=UserFeedbackDraft.create(
            match_report_id=report_id,
            job_id=job_id,
            decision=decision,
            reasons=reasons,
        ),
        created_at=created_at,
    )


class _FeedbackQueries:
    def __init__(self, items: tuple[StoredUserFeedback, ...]) -> None:
        self.items = items
        self.list_all_calls = 0

    def get(self, feedback_id: str):
        return None

    def list_for_match_report(self, match_report_id: str):
        return ()

    def list_for_job(self, job_id: str):
        return ()

    def list_all(self):
        self.list_all_calls += 1
        return self.items


def _ready() -> UserFeedbackPersistenceReadiness:
    return UserFeedbackPersistenceReadiness(ready=True, blocker_codes=())


def test_target_cohort_source_uses_latest_feedback_per_job_and_preserves_provenance() -> None:
    repository = _FeedbackQueries(
        (
            _feedback(
                "f_old",
                job_id="job_1",
                report_id="report_old",
                decision=FeedbackDecision.MAYBE,
                created_at=NOW,
            ),
            _feedback(
                "f_new",
                job_id="job_1",
                report_id="report_new",
                decision=FeedbackDecision.INTERESTED,
                created_at=NOW + timedelta(minutes=1),
            ),
            _feedback(
                "f_maybe",
                job_id="job_2",
                report_id="report_2",
                decision=FeedbackDecision.MAYBE,
                created_at=NOW,
            ),
            _feedback(
                "f_rejected",
                job_id="job_3",
                report_id="report_3",
                decision=FeedbackDecision.REJECTED,
                created_at=NOW,
            ),
        )
    )

    result = UserFeedbackTargetCohortSourceUseCase(
        feedback_repository=repository,
        persistence_readiness=_ready,
    ).execute()

    assert [(item.job_id, item.decision.value) for item in result.candidates] == [
        ("job_1", "interested"),
        ("job_2", "maybe"),
    ]
    assert result.candidates[0].feedback_id == "f_new"
    assert result.candidates[0].match_report_id == "report_new"
    assert result.total_feedback_records == 4
    assert result.latest_job_feedback_count == 3
    assert result.excluded_rejected_job_ids == ("job_3",)
    assert result.db_writes == 0
    assert result.provider_calls == 0
    assert result.trace_runs_created == 0
    assert repository.list_all_calls == 1


def test_target_cohort_source_is_stable_for_equal_timestamps() -> None:
    repository = _FeedbackQueries(
        (
            _feedback(
                "f_a",
                job_id="job_1",
                report_id="report_a",
                decision=FeedbackDecision.MAYBE,
                created_at=NOW,
            ),
            _feedback(
                "f_b",
                job_id="job_1",
                report_id="report_b",
                decision=FeedbackDecision.INTERESTED,
                created_at=NOW,
            ),
        )
    )

    result = UserFeedbackTargetCohortSourceUseCase(
        feedback_repository=repository,
        persistence_readiness=_ready,
    ).execute()

    assert len(result.candidates) == 1
    assert result.candidates[0].feedback_id == "f_b"


def test_target_cohort_source_fails_closed_before_repository_read_when_schema_missing() -> None:
    repository = _FeedbackQueries(())

    with pytest.raises(UserFeedbackPersistenceNotReadyError):
        UserFeedbackTargetCohortSourceUseCase(
            feedback_repository=repository,
            persistence_readiness=lambda: UserFeedbackPersistenceReadiness(
                ready=False,
                blocker_codes=("user_feedback_persistence_not_ready",),
            ),
        ).execute()

    assert repository.list_all_calls == 0

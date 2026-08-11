"""Tests for user-facing Target Cohort candidate projection."""
from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from app.application.job_queries.models import JobListItem, JobPage
from app.application.target_cohort_candidates import ListTargetCohortCandidatesUseCase
from app.application.user_feedback_target_cohort import (
    UserFeedbackTargetCohortCandidate,
    UserFeedbackTargetCohortSourceResult,
)
from app.domain.jobs import RemoteConfidence, RemoteStatus
from app.domain.user_feedback import FeedbackDecision, FeedbackReason


def _job(job_id: str, title: str) -> JobListItem:
    return JobListItem(
        id=job_id,
        title=title,
        company="Example AI",
        area="武汉",
        salary_min_k=20,
        salary_max_k=30,
        remote_status=RemoteStatus.UNKNOWN,
        remote_confidence=RemoteConfidence.LOW,
        source="boss",
        source_url=f"https://example.com/{job_id}",
        source_version="1",
        collected_at=None,
    )


class _Source:
    def execute(self) -> UserFeedbackTargetCohortSourceResult:
        return UserFeedbackTargetCohortSourceResult(
            candidates=(
                UserFeedbackTargetCohortCandidate(
                    job_id="job_1",
                    feedback_id="feedback_1",
                    match_report_id="match_1",
                    decision=FeedbackDecision.INTERESTED,
                    feedback_created_at=datetime(2026, 8, 10, 9, tzinfo=UTC),
                    reasons=(FeedbackReason.ROLE_FIT,),
                    note="值得重点准备",
                ),
            ),
            total_feedback_records=2,
            latest_job_feedback_count=2,
            excluded_rejected_job_ids=("job_2",),
        )


class _Jobs:
    def fetch_page(self, _query):
        return JobPage(
            total=3,
            limit=100,
            offset=0,
            items=(
                _job("job_1", "AI Agent Engineer"),
                _job("job_2", "AI Product Engineer"),
                _job("job_3", "Frontend AI Engineer"),
            ),
        )


class _Reports:
    def get(self, report_id: str):
        if report_id != "match_1":
            return None
        return SimpleNamespace(
            report=SimpleNamespace(
                recommendation=SimpleNamespace(value="good"),
                summary="Agent 工程经验较匹配，Python 仍需补强。",
            )
        )


def test_projects_all_jobs_with_feedback_as_optional_overlay() -> None:
    result = ListTargetCohortCandidatesUseCase(
        source=_Source(),
        jobs=_Jobs(),
        reports=_Reports(),
    ).execute()

    assert len(result.items) == 3
    interested, rejected, unrated = result.items
    assert interested.job_id == "job_1"
    assert interested.feedback_id == "feedback_1"
    assert interested.decision is FeedbackDecision.INTERESTED
    assert interested.reasons == (FeedbackReason.ROLE_FIT,)
    assert interested.recommendation == "good"
    assert rejected.job_id == "job_2"
    assert rejected.decision is FeedbackDecision.REJECTED
    assert rejected.feedback_id is None
    assert unrated.job_id == "job_3"
    assert unrated.decision is None
    assert result.total_job_count == 3
    assert result.excluded_rejected_job_count == 1
    assert result.feedback_overlay_available is True
    assert result.db_writes == 0
    assert result.provider_calls == 0
    assert result.trace_runs_created == 0

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from app.application.job_queries.models import JobListItem, JobListQuery, JobPage
from app.application.match_review.readiness import GetMatchReviewReadinessUseCase
from app.domain.jobs import RemoteConfidence, RemoteStatus


@dataclass(frozen=True)
class _Readiness:
    inputs_release_eligible: bool
    blockers: tuple = ()


class _Jobs:
    def execute(self, query: JobListQuery) -> JobPage:
        items = tuple(
            JobListItem(
                id=f"job_{index}",
                title=f"Role {index}",
                company="Example",
                area=None,
                salary_min_k=None,
                salary_max_k=None,
                remote_status=RemoteStatus.UNKNOWN,
                remote_confidence=RemoteConfidence.LOW,
                source="fixture",
                source_url=f"https://example.test/{index}",
                source_version=None,
                collected_at=datetime.now(timezone.utc),
            )
            for index in range(20)
        )
        return JobPage(total=20, limit=query.limit, offset=query.offset, items=items)


class _MatchInputs:
    def execute(self, job_id: str) -> _Readiness:
        return _Readiness(inputs_release_eligible=job_id in {"job_0", "job_1"})


def test_match_review_readiness_is_read_only_and_fail_closed() -> None:
    result = GetMatchReviewReadinessUseCase(
        jobs=_Jobs(),
        match_inputs=_MatchInputs(),
        persistence_ready=lambda: False,
    ).execute()

    assert result.required_job_count == 20
    assert result.available_job_count == 20
    assert result.input_ready_job_count == 2
    assert result.persistence_ready is False
    assert result.ready_for_human_review is False
    assert result.reviewable_job_ids == ("job_0", "job_1")
    assert {item.code for item in result.blockers} == {
        "match_report_persistence_not_ready",
        "insufficient_reviewable_jobs",
    }
    assert result.db_writes == 0
    assert result.provider_calls == 0
    assert result.trace_runs_created == 0


def test_match_review_readiness_requires_twenty_trusted_jobs() -> None:
    class _AllReady(_MatchInputs):
        def execute(self, job_id: str) -> _Readiness:
            return _Readiness(inputs_release_eligible=True)

    result = GetMatchReviewReadinessUseCase(
        jobs=_Jobs(),
        match_inputs=_AllReady(),
        persistence_ready=lambda: True,
    ).execute()

    assert result.ready_for_human_review is True
    assert result.input_ready_job_count == 20
    assert len(result.reviewable_job_ids) == 20
    assert result.blockers == ()

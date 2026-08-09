"""Read-only readiness for the Phase 4 twenty-job human Match review."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from app.application.job_queries.models import JobListQuery, JobPage


class JobPoolReader(Protocol):
    def execute(self, query: JobListQuery) -> JobPage: ...


class MatchInputReadinessDetail(Protocol):
    inputs_release_eligible: bool


class MatchInputReadinessReader(Protocol):
    def execute(self, job_id: str) -> MatchInputReadinessDetail: ...


@dataclass(frozen=True, slots=True)
class MatchReviewReadinessBlocker:
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class MatchReviewReadiness:
    required_job_count: int
    available_job_count: int
    input_ready_job_count: int
    persistence_ready: bool
    ready_for_human_review: bool
    reviewable_job_ids: tuple[str, ...]
    blockers: tuple[MatchReviewReadinessBlocker, ...]
    db_writes: int = 0
    provider_calls: int = 0
    trace_runs_created: int = 0


class GetMatchReviewReadinessUseCase:
    """Expose human-review blockers without running Match or mutating state."""

    REQUIRED_JOB_COUNT = 20

    def __init__(
        self,
        *,
        jobs: JobPoolReader,
        match_inputs: MatchInputReadinessReader,
        persistence_ready: Callable[[], bool],
    ) -> None:
        self._jobs = jobs
        self._match_inputs = match_inputs
        self._persistence_ready = persistence_ready

    def execute(self) -> MatchReviewReadiness:
        page = self._jobs.execute(JobListQuery(limit=self.REQUIRED_JOB_COUNT, offset=0))
        reviewable = tuple(
            item.id
            for item in page.items
            if self._match_inputs.execute(item.id).inputs_release_eligible
        )
        persistence_ready = self._persistence_ready()
        blockers: list[MatchReviewReadinessBlocker] = []
        if not persistence_ready:
            blockers.append(
                MatchReviewReadinessBlocker(
                    code="match_report_persistence_not_ready",
                    message="MatchReport persistence schema is not ready.",
                )
            )
        if len(reviewable) < self.REQUIRED_JOB_COUNT:
            blockers.append(
                MatchReviewReadinessBlocker(
                    code="insufficient_reviewable_jobs",
                    message=(
                        f"Need {self.REQUIRED_JOB_COUNT} trusted jobs for human Match review; "
                        f"currently {len(reviewable)} are input-ready."
                    ),
                )
            )
        return MatchReviewReadiness(
            required_job_count=self.REQUIRED_JOB_COUNT,
            available_job_count=page.total,
            input_ready_job_count=len(reviewable),
            persistence_ready=persistence_ready,
            ready_for_human_review=not blockers,
            reviewable_job_ids=reviewable,
            blockers=tuple(blockers),
        )

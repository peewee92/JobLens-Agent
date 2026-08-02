"""Pure application tests for Job Pool query use cases."""
from datetime import UTC, datetime

import pytest

from app.application.job_queries import (
    JobDetail,
    JobListItem,
    JobListQuery,
    JobNotFoundError,
    JobPage,
)
from app.application.job_queries.use_cases import GetJobUseCase, ListJobsUseCase
from app.application.ports import AbstractJobQueryRepository
from app.domain.jobs import RemoteConfidence, RemoteStatus


class FakeJobQueryRepository(AbstractJobQueryRepository):
    def __init__(self) -> None:
        self.received_query: JobListQuery | None = None
        self.page = JobPage(total=0, limit=20, offset=0, items=())
        self.detail: JobDetail | None = None

    def fetch_page(self, query: JobListQuery) -> JobPage:
        self.received_query = query
        return self.page

    def get_job(self, job_id: str) -> JobDetail | None:
        if self.detail is not None and self.detail.id == job_id:
            return self.detail
        return None


def make_item() -> JobListItem:
    return JobListItem(
        id="job_1",
        title="AI Engineer",
        company="Example",
        area="武汉",
        salary_min_k=20,
        salary_max_k=30,
        remote_status=RemoteStatus.UNKNOWN,
        remote_confidence=RemoteConfidence.LOW,
        source="boss",
        source_url="https://example.test/job/1",
        source_version="1.3.1",
        collected_at=datetime(2026, 8, 2, tzinfo=UTC),
    )


def make_detail() -> JobDetail:
    item = make_item()
    return JobDetail(
        id=item.id,
        title=item.title,
        company=item.company,
        area=item.area,
        salary_min_k=item.salary_min_k,
        salary_max_k=item.salary_max_k,
        experience="3-5年",
        education="本科",
        description="Build AI applications",
        skills=("Python",),
        remote_status=item.remote_status,
        remote_confidence=item.remote_confidence,
        source=item.source,
        source_url=item.source_url,
        source_version=item.source_version,
        collected_at=item.collected_at,
    )


def test_list_use_case_delegates_query_and_returns_page() -> None:
    repository = FakeJobQueryRepository()
    query = JobListQuery(city="武汉", limit=10)
    repository.page = JobPage(total=1, limit=10, offset=0, items=(make_item(),))

    result = ListJobsUseCase(repository).execute(query)

    assert repository.received_query == query
    assert result.total == 1
    assert result.items[0].id == "job_1"


def test_get_use_case_returns_detail() -> None:
    repository = FakeJobQueryRepository()
    repository.detail = make_detail()

    result = GetJobUseCase(repository).execute("job_1")

    assert result.id == "job_1"
    assert result.skills == ("Python",)


def test_get_use_case_raises_expected_not_found_error() -> None:
    repository = FakeJobQueryRepository()

    with pytest.raises(JobNotFoundError, match="Job not found: job_missing"):
        GetJobUseCase(repository).execute("job_missing")

"""Application tests for Job Import audit detail queries."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.application.job_import_queries import (
    JobImportCandidateSummary,
    JobImportDetail,
    JobImportNotFoundError,
)
from app.application.job_import_queries.use_cases import GetJobImportDetailUseCase
from app.application.ports.job_import_query_repository import (
    AbstractJobImportQueryRepository,
)


class StubRepository(AbstractJobImportQueryRepository):
    def __init__(self, detail: JobImportDetail | None) -> None:
        self.detail = detail
        self.requested_ids: list[str] = []

    def get_import(self, import_id: str) -> JobImportDetail | None:
        self.requested_ids.append(import_id)
        return self.detail


def make_detail() -> JobImportDetail:
    now = datetime(2026, 8, 2, 12, 0, tzinfo=UTC)
    return JobImportDetail(
        import_id="imp_test",
        source_version="1.3.1",
        collector_version="1.3.1",
        received=0,
        created=0,
        updated=0,
        skipped=0,
        errors=(),
        search_intent_snapshot={},
        source_snapshot={},
        candidate_summary=JobImportCandidateSummary(
            total=0,
            kept=0,
            rejected=0,
            unknown=0,
        ),
        collected_at=now,
        created_at=now,
        items=(),
    )


def test_get_import_detail_returns_repository_read_model() -> None:
    detail = make_detail()
    repository = StubRepository(detail)

    result = GetJobImportDetailUseCase(repository).execute("imp_test")

    assert result is detail
    assert repository.requested_ids == ["imp_test"]


def test_get_import_detail_raises_stable_not_found_error() -> None:
    repository = StubRepository(None)

    with pytest.raises(JobImportNotFoundError, match="imp_missing"):
        GetJobImportDetailUseCase(repository).execute("imp_missing")

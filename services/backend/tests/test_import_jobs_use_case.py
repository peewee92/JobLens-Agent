"""End-to-end application tests for ImportJobsUseCase without HTTP."""
from __future__ import annotations

from collections.abc import Iterator
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.application.job_imports import ImportJobsUseCase
from app.application.job_imports.adapter import adapt_collector_report
from app.application.job_imports.errors import (
    ImportIdentityConflictError,
    UnsupportedCollectorVersionError,
)
from app.application.job_imports.normalizer import normalize_adapted_report
from app.db.base import Base
from app.db.models import (
    JobImportCandidateORM,
    JobImportItemORM,
    JobImportORM,
    JobORM,
    JobSourceORM,
)
from app.domain.jobs import ImportOutcome
from app.repositories import SqlAlchemyUnitOfWork

SAMPLE_REPORT = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "samples"
    / "collector-report-minimal.json"
)


@pytest.fixture
def session_factory(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'import-use-case.db'}"
    engine = create_engine(database_url)

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    yield factory
    Base.metadata.drop_all(engine)
    engine.dispose()


def load_report() -> dict:
    return json.loads(SAMPLE_REPORT.read_text(encoding="utf-8"))


def make_use_case(
    session_factory: sessionmaker[Session],
) -> ImportJobsUseCase:
    return ImportJobsUseCase(lambda: SqlAlchemyUnitOfWork(session_factory))


def count_rows(session: Session, model: type) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


def test_use_case_commits_exactly_once_per_completed_batch(
    session_factory: sessionmaker[Session],
) -> None:
    commit_calls = 0

    class CountingUnitOfWork(SqlAlchemyUnitOfWork):
        def commit(self) -> None:
            nonlocal commit_calls
            commit_calls += 1
            super().commit()

    use_case = ImportJobsUseCase(lambda: CountingUnitOfWork(session_factory))
    result = use_case.execute(load_report())

    assert result.received == 1
    assert commit_calls == 1


def test_first_import_creates_complete_audit_graph(
    session_factory: sessionmaker[Session],
) -> None:
    result = make_use_case(session_factory).execute(load_report())

    assert result.received == 1
    assert result.created == 1
    assert result.updated == 0
    assert result.skipped == 0
    assert result.errors == ()

    with session_factory() as session:
        batch = session.get(JobImportORM, result.import_id)
        item = session.scalar(select(JobImportItemORM))
        job = session.scalar(select(JobORM))
        source = session.scalar(select(JobSourceORM))

        assert batch is not None
        assert item is not None
        assert job is not None
        assert source is not None
        assert batch.received == batch.created + batch.updated + batch.skipped
        assert batch.created == 1
        assert batch.errors == []
        assert batch.search_intent_snapshot["selectedCities"][0]["name"] == "武汉"
        assert item.input_index == 0
        assert item.outcome is ImportOutcome.CREATED
        assert item.job_id == job.id
        assert item.job_source_id == source.id
        assert source.job_id == job.id


def test_reimport_updates_stable_entities_but_creates_new_audit_batch(
    session_factory: sessionmaker[Session],
) -> None:
    use_case = make_use_case(session_factory)
    first_result = use_case.execute(load_report())

    second_payload = load_report()
    second_payload["generatedAt"] = "2026-07-22T00:00:00.000Z"
    second_payload["jobs"][0]["title"] = "高级 AI 应用开发工程师"
    second_payload["jobs"][0]["salaryMinK"] = 20
    second_result = use_case.execute(second_payload)

    assert first_result.created == 1
    assert second_result.created == 0
    assert second_result.updated == 1
    assert second_result.skipped == 0
    assert first_result.import_id != second_result.import_id

    with session_factory() as session:
        assert count_rows(session, JobORM) == 1
        assert count_rows(session, JobSourceORM) == 1
        assert count_rows(session, JobImportORM) == 2
        assert count_rows(session, JobImportItemORM) == 2
        assert count_rows(session, JobImportCandidateORM) == 0

        job = session.scalar(select(JobORM))
        source = session.scalar(select(JobSourceORM))
        items = list(
            session.scalars(
                select(JobImportItemORM).order_by(JobImportItemORM.created_at)
            )
        )
        assert job is not None
        assert source is not None
        assert job.title == "高级 AI 应用开发工程师"
        assert job.salary_min_k == 20
        assert source.source_raw["title"] == "高级 AI 应用开发工程师"
        assert source.first_seen_at == datetime(2026, 7, 21, tzinfo=timezone.utc).replace(
            tzinfo=None
        )
        assert source.last_seen_at == datetime(2026, 7, 22, tzinfo=timezone.utc).replace(
            tzinfo=None
        )
        assert [item.outcome for item in items] == [
            ImportOutcome.CREATED,
            ImportOutcome.UPDATED,
        ]


def test_candidates_are_preserved_without_entering_job_pool(
    session_factory: sessionmaker[Session],
) -> None:
    payload = load_report()
    payload["candidates"] = [
        {
            "title": "Kept candidate",
            "company": "Company A",
            "url": "https://www.zhipin.com/job_detail/candidate-a.html",
            "sourceJobId": "candidate-a",
            "keep": True,
            "decision": "keep:matched",
            "pendingDetail": False,
            "unknownNested": {"score": 0.92},
        },
        {
            "title": "Rejected candidate",
            "company": "Company B",
            "url": "https://www.zhipin.com/job_detail/candidate-b.html",
            "keep": False,
            "decision": "reject:salary",
            "pendingDetail": True,
        },
        "legacy-candidate-value",
        None,
    ]

    result = make_use_case(session_factory).execute(payload)

    with session_factory() as session:
        rows = list(
            session.scalars(
                select(JobImportCandidateORM).order_by(
                    JobImportCandidateORM.candidate_index
                )
            )
        )
        assert count_rows(session, JobORM) == 1
        assert len(rows) == 4
        assert [row.candidate_index for row in rows] == [0, 1, 2, 3]
        assert [row.keep for row in rows] == [True, False, None, None]
        assert rows[0].decision == "keep:matched"
        assert rows[0].source_job_id == "candidate-a"
        assert rows[0].candidate_raw["unknownNested"] == {"score": 0.92}
        assert rows[1].pending_detail is True
        assert rows[2].candidate_raw == "legacy-candidate-value"
        assert rows[3].candidate_raw is None
        assert all(row.import_id == result.import_id for row in rows)


def test_reimport_creates_new_candidate_snapshot_per_batch(
    session_factory: sessionmaker[Session],
) -> None:
    payload = load_report()
    payload["candidates"] = [{"title": "Candidate", "keep": True}]
    use_case = make_use_case(session_factory)

    first = use_case.execute(payload)
    second = use_case.execute(payload)

    with session_factory() as session:
        rows = list(
            session.scalars(
                select(JobImportCandidateORM).order_by(
                    JobImportCandidateORM.created_at,
                    JobImportCandidateORM.id,
                )
            )
        )
        assert len(rows) == 2
        assert {row.import_id for row in rows} == {first.import_id, second.import_id}
        assert rows[0].candidate_raw == rows[1].candidate_raw
        assert count_rows(session, JobORM) == 1


def test_item_error_is_audited_and_counted_as_skipped(
    session_factory: sessionmaker[Session],
) -> None:
    payload = load_report()
    invalid_job = deepcopy(payload["jobs"][0])
    invalid_job.pop("company")
    payload["jobs"].append(invalid_job)

    result = make_use_case(session_factory).execute(payload)

    assert result.received == 2
    assert result.created == 1
    assert result.updated == 0
    assert result.skipped == 1
    assert len(result.errors) == 1
    assert result.errors[0].index == 1
    assert result.errors[0].code == "invalid_job_payload"

    with session_factory() as session:
        batch = session.get(JobImportORM, result.import_id)
        items = list(
            session.scalars(
                select(JobImportItemORM).order_by(JobImportItemORM.input_index)
            )
        )
        assert batch is not None
        assert batch.received == 2
        assert batch.received == batch.created + batch.updated + batch.skipped
        assert batch.errors[0]["index"] == 1
        assert [item.outcome for item in items] == [
            ImportOutcome.CREATED,
            ImportOutcome.ERROR,
        ]
        assert items[1].error_code == "invalid_job_payload"


def test_identity_conflict_rolls_back_new_batch_and_all_new_rows(
    session_factory: sessionmaker[Session],
) -> None:
    payload = load_report()
    payload["candidates"] = [{"title": "must rollback", "keep": False}]
    normalized = normalize_adapted_report(adapt_collector_report(payload)).jobs[0]
    conflicting = replace(
        normalized,
        canonical_key="v1:boss:id:legacy-job",
        title="Legacy Job",
    )

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        existing_job_id = uow.jobs.add_job(conflicting)
        uow.jobs.add_source(existing_job_id, conflicting)
        uow.commit()

    with pytest.raises(ImportIdentityConflictError):
        make_use_case(session_factory).execute(payload)

    with session_factory() as session:
        assert count_rows(session, JobORM) == 1
        assert count_rows(session, JobSourceORM) == 1
        assert count_rows(session, JobImportORM) == 0
        assert count_rows(session, JobImportItemORM) == 0
        assert count_rows(session, JobImportCandidateORM) == 0
        job = session.scalar(select(JobORM))
        assert job is not None
        assert job.title == "Legacy Job"


def test_unsupported_report_version_opens_no_transaction_or_audit_batch(
    session_factory: sessionmaker[Session],
) -> None:
    payload = load_report()
    payload["version"] = "9.9.9"

    with pytest.raises(UnsupportedCollectorVersionError):
        make_use_case(session_factory).execute(payload)

    with session_factory() as session:
        assert count_rows(session, JobImportORM) == 0
        assert count_rows(session, JobImportItemORM) == 0
        assert count_rows(session, JobImportCandidateORM) == 0

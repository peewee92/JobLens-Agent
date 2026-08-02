"""SQLAlchemy query tests for Job Import audit details."""
from __future__ import annotations

from collections.abc import Iterator
from copy import deepcopy
import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.application.job_imports import ImportJobsUseCase
from app.db.base import Base
from app.db.models import JobImportItemORM, JobImportORM, JobORM, JobSourceORM
from app.domain.jobs import ImportOutcome
from app.repositories import (
    SqlAlchemyJobImportQueryRepository,
    SqlAlchemyUnitOfWork,
)

SAMPLE_REPORT = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "samples"
    / "collector-report-minimal.json"
)


@pytest.fixture
def session_factory(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'job-import-query.db'}"
    )

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


def seed_mixed_import(session_factory: sessionmaker[Session]) -> str:
    payload = load_report()
    invalid = deepcopy(payload["jobs"][0])
    invalid.pop("company")
    payload["jobs"].append(invalid)
    use_case = ImportJobsUseCase(
        lambda: SqlAlchemyUnitOfWork(session_factory)
    )
    return use_case.execute(payload).import_id


def test_get_import_returns_ordered_public_audit_detail(
    session_factory: sessionmaker[Session],
) -> None:
    import_id = seed_mixed_import(session_factory)

    detail = SqlAlchemyJobImportQueryRepository(session_factory).get_import(import_id)

    assert detail is not None
    assert detail.import_id == import_id
    assert detail.source_version == "1.3.1"
    assert detail.collector_version == "1.3.1"
    assert detail.received == 2
    assert detail.created == 1
    assert detail.updated == 0
    assert detail.skipped == 1
    assert detail.received == detail.created + detail.updated + detail.skipped
    assert detail.search_intent_snapshot["selectedCities"][0]["name"] == "武汉"
    assert detail.source_snapshot["candidateCount"] == 0
    assert [item.input_index for item in detail.items] == [0, 1]
    assert [item.outcome for item in detail.items] == [
        ImportOutcome.CREATED,
        ImportOutcome.ERROR,
    ]
    assert detail.items[0].job_id is not None
    assert detail.items[0].job_source_id is not None
    assert detail.items[1].error_code == "invalid_job_payload"
    assert len(detail.errors) == 1
    assert detail.errors[0].index == 1
    assert detail.errors[0].stage == "adapter"

    # The database keeps raw diagnostic evidence, but the public Read Model does not.
    with session_factory() as session:
        batch = session.get(JobImportORM, import_id)
        assert batch is not None
        assert "raw" in batch.errors[0]
    assert not hasattr(detail.errors[0], "raw")


def test_get_import_uses_two_selects_and_performs_no_writes(
    session_factory: sessionmaker[Session],
) -> None:
    import_id = seed_mixed_import(session_factory)
    engine = session_factory.kw["bind"]
    select_count = 0
    write_statements: list[str] = []

    @event.listens_for(engine, "before_cursor_execute")
    def _count_sql(_conn, _cursor, statement, _parameters, _context, _many) -> None:
        nonlocal select_count
        verb = statement.lstrip().split(maxsplit=1)[0].upper()
        if verb == "SELECT":
            select_count += 1
        elif verb in {"INSERT", "UPDATE", "DELETE"}:
            write_statements.append(verb)

    try:
        before = {}
        with session_factory() as session:
            for model in (JobORM, JobSourceORM, JobImportORM, JobImportItemORM):
                before[model] = int(
                    session.scalar(select(func.count()).select_from(model)) or 0
                )
        select_count = 0

        detail = SqlAlchemyJobImportQueryRepository(session_factory).get_import(import_id)

        assert detail is not None
        assert select_count == 2
        assert write_statements == []
        with session_factory() as session:
            for model, expected in before.items():
                assert int(
                    session.scalar(select(func.count()).select_from(model)) or 0
                ) == expected
    finally:
        event.remove(engine, "before_cursor_execute", _count_sql)


def test_get_import_returns_none_for_unknown_id(
    session_factory: sessionmaker[Session],
) -> None:
    repository = SqlAlchemyJobImportQueryRepository(session_factory)

    assert repository.get_import("imp_missing") is None

"""Transaction-boundary tests for the SQLAlchemy Unit of Work."""
from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.application.job_imports.models import NormalizedJobInput
from app.application.ports import JobImportItemWrite, JobImportWrite
from app.db.base import Base
from app.db.models import JobImportItemORM, JobImportORM, JobORM, JobSourceORM
from app.domain.jobs import ImportOutcome, RemoteConfidence, RemoteStatus
from app.repositories import SqlAlchemyUnitOfWork


@pytest.fixture
def session_factory(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'unit-of-work.db'}"
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


def make_job_input() -> NormalizedJobInput:
    observed_at = datetime(2026, 8, 2, 6, 0, tzinfo=timezone.utc)
    return NormalizedJobInput(
        source="boss",
        source_version="1.3.1",
        source_job_id="uow-job",
        source_url="https://www.zhipin.com/job_detail/uow-job.html",
        normalized_source_url="https://www.zhipin.com/job_detail/uow-job.html",
        source_raw={"title": "AI Engineer"},
        canonical_key="v1:boss:id:uow-job",
        canonical_key_version="v1",
        title="AI Engineer",
        company="Example Co",
        area="武汉",
        salary_min_k=20,
        salary_max_k=30,
        experience="3-5年",
        education="本科",
        description="Build reliable AI applications",
        skills=("Python", "SQLAlchemy"),
        remote_status=RemoteStatus.UNKNOWN,
        remote_confidence=RemoteConfidence.LOW,
        collected_at=observed_at,
        first_seen_at=observed_at,
        last_seen_at=observed_at,
    )


def count_rows(session_factory: sessionmaker[Session], model: type) -> int:
    with session_factory() as session:
        return int(session.scalar(select(func.count()).select_from(model)) or 0)


def test_explicit_commit_persists_complete_transaction(
    session_factory: sessionmaker[Session],
) -> None:
    normalized = make_job_input()

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        import_id = uow.jobs.add_import(
            JobImportWrite(source_version="1.3.1", received=1)
        )
        job_id = uow.jobs.add_job(normalized)
        source_id = uow.jobs.add_source(job_id, normalized)
        uow.jobs.add_import_item(
            JobImportItemWrite(
                import_id=import_id,
                input_index=0,
                outcome=ImportOutcome.CREATED,
                job_id=job_id,
                job_source_id=source_id,
            )
        )
        uow.commit()

    assert count_rows(session_factory, JobORM) == 1
    assert count_rows(session_factory, JobSourceORM) == 1
    assert count_rows(session_factory, JobImportORM) == 1
    assert count_rows(session_factory, JobImportItemORM) == 1


def test_exit_without_commit_rolls_back_all_changes(
    session_factory: sessionmaker[Session],
) -> None:
    normalized = make_job_input()

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        job_id = uow.jobs.add_job(normalized)
        uow.jobs.add_source(job_id, normalized)
        # Intentionally omit commit.

    assert count_rows(session_factory, JobORM) == 0
    assert count_rows(session_factory, JobSourceORM) == 0


def test_exception_rolls_back_complete_graph(
    session_factory: sessionmaker[Session],
) -> None:
    normalized = make_job_input()

    with pytest.raises(RuntimeError, match="simulated source failure"):
        with SqlAlchemyUnitOfWork(session_factory) as uow:
            import_id = uow.jobs.add_import(
                JobImportWrite(source_version="1.3.1", received=1)
            )
            job_id = uow.jobs.add_job(normalized)
            source_id = uow.jobs.add_source(job_id, normalized)
            uow.jobs.add_import_item(
                JobImportItemWrite(
                    import_id=import_id,
                    input_index=0,
                    outcome=ImportOutcome.CREATED,
                    job_id=job_id,
                    job_source_id=source_id,
                )
            )
            raise RuntimeError("simulated source failure")

    assert count_rows(session_factory, JobORM) == 0
    assert count_rows(session_factory, JobSourceORM) == 0
    assert count_rows(session_factory, JobImportORM) == 0
    assert count_rows(session_factory, JobImportItemORM) == 0


def test_uow_cannot_be_used_outside_active_scope(
    session_factory: sessionmaker[Session],
) -> None:
    uow = SqlAlchemyUnitOfWork(session_factory)

    with pytest.raises(RuntimeError, match="not active"):
        uow.commit()

    with uow:
        pass

    with pytest.raises(RuntimeError, match="not active"):
        uow.rollback()

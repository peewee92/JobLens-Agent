"""Repository behavior tests independent from HTTP and future use cases."""
from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.application.job_imports.models import NormalizedJobInput
from app.application.ports import (
    JobImportItemWrite,
    JobImportWrite,
    RepositoryRecordNotFound,
)
from app.db.base import Base
from app.db.models import JobImportItemORM, JobImportORM, JobORM, JobSourceORM
from app.domain.jobs import ImportOutcome, RemoteConfidence, RemoteStatus
from app.repositories import SqlAlchemyJobRepository


@pytest.fixture
def session_factory(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'repository.db'}"
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


def make_job_input(*, title: str = "AI Application Engineer") -> NormalizedJobInput:
    collected_at = datetime(2026, 8, 2, 6, 0, tzinfo=timezone.utc)
    return NormalizedJobInput(
        source="boss",
        source_version="1.3.1",
        source_job_id="abc123",
        source_url="https://www.zhipin.com/job_detail/abc123.html?ka=search",
        normalized_source_url="https://www.zhipin.com/job_detail/abc123.html",
        source_raw={"title": title, "collectorOnlyField": "preserved"},
        canonical_key="v1:boss:id:abc123",
        canonical_key_version="v1",
        title=title,
        company="Example Co",
        area="武汉",
        salary_min_k=18,
        salary_max_k=30,
        experience="3-5年",
        education="本科",
        description="Build AI applications",
        skills=("Python", "FastAPI"),
        remote_status=RemoteStatus.UNKNOWN,
        remote_confidence=RemoteConfidence.LOW,
        collected_at=collected_at,
        first_seen_at=collected_at,
        last_seen_at=collected_at,
    )


def test_repository_flushes_but_does_not_commit(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        repository = SqlAlchemyJobRepository(session)
        job_id = repository.add_job(make_job_input())

        assert job_id.startswith("job_")
        assert session.get(JobORM, job_id) is not None
        assert session.in_transaction()
        # Closing this Session without commit must roll the flushed INSERT back.

    with session_factory() as verification_session:
        assert verification_session.get(JobORM, job_id) is None


def test_repository_supports_idempotency_lookups_and_updates(
    session_factory: sessionmaker[Session],
) -> None:
    original = make_job_input()
    with session_factory() as session:
        repository = SqlAlchemyJobRepository(session)
        job_id = repository.add_job(original)
        source_id = repository.add_source(job_id, original)
        session.commit()

    changed = make_job_input(title="Senior AI Application Engineer")
    changed = replace(
        changed,
        salary_min_k=22,
        last_seen_at=changed.last_seen_at + timedelta(days=1),
    )

    with session_factory() as session:
        repository = SqlAlchemyJobRepository(session)
        assert repository.find_job_id_by_canonical_key(original.canonical_key) == job_id
        source_by_external_id = repository.find_source_by_external_id(
            original.source, original.source_job_id or ""
        )
        source_by_url = repository.find_source_by_normalized_url(
            original.source, original.normalized_source_url
        )
        assert source_by_external_id is not None
        assert source_by_external_id.id == source_id
        assert source_by_external_id.job_id == job_id
        assert source_by_url == source_by_external_id

        repository.update_job(job_id, changed)
        repository.update_source(source_id, changed)
        session.commit()

    with session_factory() as session:
        job = session.get(JobORM, job_id)
        source = session.get(JobSourceORM, source_id)
        assert job is not None
        assert source is not None
        assert job.title == "Senior AI Application Engineer"
        assert job.salary_min_k == 22
        assert source.last_seen_at == changed.last_seen_at.replace(tzinfo=None)
        assert source.first_seen_at == original.first_seen_at.replace(tzinfo=None)
        assert source.source_raw["collectorOnlyField"] == "preserved"


def test_repository_writes_import_batch_and_per_item_audit(
    session_factory: sessionmaker[Session],
) -> None:
    normalized = make_job_input()
    with session_factory() as session:
        repository = SqlAlchemyJobRepository(session)
        import_id = repository.add_import(
            JobImportWrite(
                source_version="1.3.1",
                collector_version="1.3.1",
                received=1,
                source_snapshot={"keywords": ["AI 应用开发"]},
                collected_at=normalized.collected_at,
            )
        )
        job_id = repository.add_job(normalized)
        source_id = repository.add_source(job_id, normalized)
        item_id = repository.add_import_item(
            JobImportItemWrite(
                import_id=import_id,
                input_index=0,
                outcome=ImportOutcome.CREATED,
                job_id=job_id,
                job_source_id=source_id,
            )
        )
        repository.update_import_summary(
            import_id,
            created=1,
            updated=0,
            skipped=0,
            errors=(),
        )
        session.commit()

    with session_factory() as session:
        batch = session.get(JobImportORM, import_id)
        item = session.get(JobImportItemORM, item_id)
        assert batch is not None
        assert item is not None
        assert batch.received == 1
        assert batch.created == 1
        assert item.job_id == job_id
        assert item.job_source_id == source_id
        assert session.scalar(select(func.count(JobORM.id))) == 1


def test_repository_update_missing_record_fails_explicitly(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        repository = SqlAlchemyJobRepository(session)
        with pytest.raises(RepositoryRecordNotFound, match="Job not found"):
            repository.update_job("job_missing", make_job_input())

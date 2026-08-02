"""ORM model tests for the P0-1 job data foundation."""
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models import JobImportItemORM, JobImportORM, JobORM, JobSourceORM
from app.domain.jobs import ImportOutcome, RemoteConfidence, RemoteStatus


@pytest.fixture
def model_session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_metadata_contains_job_data_foundation_tables() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    assert set(inspect(engine).get_table_names()) == {
        "jobs",
        "job_sources",
        "job_imports",
        "job_import_items",
    }

    engine.dispose()


def test_persist_complete_job_import_graph(model_session: Session) -> None:
    job = JobORM(
        canonical_key="v1:boss:id:abc123",
        title="AI Application Engineer",
        company="Example Co",
        area="武汉",
        salary_min_k=18,
        salary_max_k=30,
        skills=["Python", "FastAPI"],
        remote_status=RemoteStatus.UNKNOWN,
        remote_confidence=RemoteConfidence.LOW,
    )
    source = JobSourceORM(
        source="boss",
        source_job_id="abc123",
        source_url="https://www.zhipin.com/job_detail/abc123.html",
        normalized_source_url="https://www.zhipin.com/job_detail/abc123.html",
        source_version="1.3.1",
        source_raw={"title": "AI Application Engineer"},
    )
    job.sources.append(source)

    import_batch = JobImportORM(
        source_version="1.3.1",
        collector_version="1.3.1",
        received=1,
        created=1,
        errors=[],
        search_intent_snapshot={"cities": ["武汉"]},
        source_snapshot={"keywords": ["AI 应用开发"]},
    )
    import_item = JobImportItemORM(
        input_index=0,
        outcome=ImportOutcome.CREATED,
        job=job,
        job_source=source,
    )
    import_batch.items.append(import_item)

    model_session.add_all([job, import_batch])
    model_session.commit()

    assert job.id.startswith("job_")
    assert source.id.startswith("src_")
    assert import_batch.id.startswith("imp_")
    assert import_item.id.startswith("itm_")
    assert source.job_id == job.id
    assert import_item.import_id == import_batch.id
    assert import_item.job_id == job.id
    assert import_item.job_source_id == source.id
    assert job.remote_status is RemoteStatus.UNKNOWN
    assert import_item.outcome is ImportOutcome.CREATED


def test_canonical_key_is_unique(model_session: Session) -> None:
    model_session.add_all(
        [
            JobORM(
                canonical_key="v1:boss:id:duplicate",
                title="AI Engineer",
                company="Company A",
            ),
            JobORM(
                canonical_key="v1:boss:id:duplicate",
                title="AI Engineer",
                company="Company A",
            ),
        ]
    )

    with pytest.raises(IntegrityError):
        model_session.commit()

    model_session.rollback()


def test_invalid_salary_range_is_rejected(model_session: Session) -> None:
    model_session.add(
        JobORM(
            canonical_key="v1:boss:id:bad-salary",
            title="AI Engineer",
            company="Company A",
            salary_min_k=30,
            salary_max_k=20,
        )
    )

    with pytest.raises(IntegrityError):
        model_session.commit()

    model_session.rollback()


def test_import_item_index_is_unique_within_batch(model_session: Session) -> None:
    import_batch = JobImportORM(
        source_version="1.3.1",
        errors=[],
        search_intent_snapshot={},
        source_snapshot={},
    )
    import_batch.items.extend(
        [
            JobImportItemORM(input_index=0, outcome=ImportOutcome.SKIPPED),
            JobImportItemORM(input_index=0, outcome=ImportOutcome.ERROR),
        ]
    )
    model_session.add(import_batch)

    with pytest.raises(IntegrityError):
        model_session.commit()

    model_session.rollback()

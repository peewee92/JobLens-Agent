"""Persistence and versioning tests for Job Requirement Extraction."""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.application.job_requirements.use_cases import (
    ExtractJobRequirementsUseCase,
    GetJobRequirementExtractionUseCase,
    GetLatestJobRequirementsUseCase,
)
from app.db.base import Base
from app.db.models import (
    JobORM,
    JobRequirementExtractionORM,
    JobRequirementORM,
    JobSourceORM,
    TraceSpanORM,
)
from app.domain.jobs import RemoteConfidence, RemoteStatus
from app.llm import FixtureJobRequirementExtractor
from app.repositories import (
    SqlAlchemyJobQueryRepository,
    SqlAlchemyJobRequirementQueryRepository,
    SqlAlchemyJobRequirementUnitOfWork,
    SqlAlchemyTraceUnitOfWork,
)
from app.workflows import ExtractJobRequirementsWorkflow


@pytest.fixture
def session_factory(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'requirements.db'}")

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


def _seed_job(
    factory: sessionmaker[Session],
    *,
    suffix: str,
    description: str,
) -> str:
    job = JobORM(
        id=f"job_{suffix}",
        canonical_key=f"v1:test:id:{suffix}",
        title="AI Application Engineer",
        company="Example Co",
        description=description,
        skills=[],
        remote_status=RemoteStatus.UNKNOWN,
        remote_confidence=RemoteConfidence.LOW,
    )
    job.sources.append(
        JobSourceORM(
            id=f"src_{suffix}",
            source="fixture",
            source_job_id=suffix,
            source_url=f"https://example.test/jobs/{suffix}",
            normalized_source_url=f"https://example.test/jobs/{suffix}",
            source_version="test",
            source_raw={},
        )
    )
    with factory() as session:
        session.add(job)
        session.commit()
    return job.id


def _use_case(factory: sessionmaker[Session]) -> ExtractJobRequirementsUseCase:
    jobs = SqlAlchemyJobQueryRepository(factory)
    query = SqlAlchemyJobRequirementQueryRepository(factory)
    workflow = ExtractJobRequirementsWorkflow(
        FixtureJobRequirementExtractor(),
        lambda: SqlAlchemyTraceUnitOfWork(factory),
    )
    return ExtractJobRequirementsUseCase(
        jobs=jobs,
        workflow=workflow,
        uow_factory=lambda: SqlAlchemyJobRequirementUnitOfWork(factory),
        query_repository=query,
        provider="fixture",
    )


def test_repeated_extraction_creates_new_run_and_preserves_history(
    session_factory: sessionmaker[Session],
) -> None:
    job_id = _seed_job(
        session_factory,
        suffix="versioned",
        description=(
            "岗位要求：\n"
            "熟练掌握 Python 和 FastAPI。\n"
            "具备 3 年以上后端开发经验。\n"
            "有 Docker 使用经验者优先。"
        ),
    )
    use_case = _use_case(session_factory)

    first = use_case.execute(job_id)
    second = use_case.execute(job_id)

    assert first.extraction_id != second.extraction_id
    assert first.input_hash == second.input_hash
    assert first.trace_run_id != second.trace_run_id
    assert first.requirement_count == len(first.requirements)
    query = SqlAlchemyJobRequirementQueryRepository(session_factory)
    latest = GetLatestJobRequirementsUseCase(
        jobs=SqlAlchemyJobQueryRepository(session_factory),
        repository=query,
    ).execute(job_id)
    historical = GetJobRequirementExtractionUseCase(
        jobs=SqlAlchemyJobQueryRepository(session_factory),
        repository=query,
    ).execute(job_id=job_id, extraction_id=first.extraction_id)

    assert latest.extraction_id == second.extraction_id
    assert historical.extraction_id == first.extraction_id
    with session_factory() as session:
        assert int(
            session.scalar(
                select(func.count()).select_from(JobRequirementExtractionORM)
            )
            or 0
        ) == 2
        assert int(
            session.scalar(select(func.count()).select_from(TraceSpanORM)) or 0
        ) == 2
        assert int(
            session.scalar(select(func.count()).select_from(JobRequirementORM)) or 0
        ) == first.requirement_count + second.requirement_count


def test_job_delete_cascades_extractions_and_requirements(
    session_factory: sessionmaker[Session],
) -> None:
    job_id = _seed_job(
        session_factory,
        suffix="cascade",
        description="岗位要求熟练掌握 Python 和 FastAPI，并具备三年以上后端开发经验。",
    )
    _use_case(session_factory).execute(job_id)

    with session_factory() as session:
        job = session.get(JobORM, job_id)
        assert job is not None
        session.delete(job)
        session.commit()
    with session_factory() as session:
        assert int(
            session.scalar(
                select(func.count()).select_from(JobRequirementExtractionORM)
            )
            or 0
        ) == 0
        assert int(
            session.scalar(select(func.count()).select_from(JobRequirementORM)) or 0
        ) == 0
        assert int(
            session.scalar(select(func.count()).select_from(TraceSpanORM)) or 0
        ) == 1


class _FailingRequirementUnitOfWork(SqlAlchemyJobRequirementUnitOfWork):
    def __enter__(self):
        super().__enter__()
        original = self.requirements

        class _RepositoryProxy:
            def add(_self, extraction) -> None:
                original.add(extraction)
                raise RuntimeError("simulated persistence failure")

        self.requirements = _RepositoryProxy()
        return self


def test_persistence_failure_rolls_back_run_but_keeps_provider_trace(
    session_factory: sessionmaker[Session],
) -> None:
    job_id = _seed_job(
        session_factory,
        suffix="rollback",
        description="岗位要求熟练掌握 Python 和 FastAPI，并具备三年以上后端开发经验。",
    )
    jobs = SqlAlchemyJobQueryRepository(session_factory)
    query = SqlAlchemyJobRequirementQueryRepository(session_factory)
    use_case = ExtractJobRequirementsUseCase(
        jobs=jobs,
        workflow=ExtractJobRequirementsWorkflow(
            FixtureJobRequirementExtractor(),
            lambda: SqlAlchemyTraceUnitOfWork(session_factory),
        ),
        uow_factory=lambda: _FailingRequirementUnitOfWork(session_factory),
        query_repository=query,
        provider="fixture",
    )

    with pytest.raises(RuntimeError, match="simulated persistence failure"):
        use_case.execute(job_id)

    with session_factory() as session:
        assert int(
            session.scalar(
                select(func.count()).select_from(JobRequirementExtractionORM)
            )
            or 0
        ) == 0
        assert int(
            session.scalar(select(func.count()).select_from(JobRequirementORM)) or 0
        ) == 0
        assert int(
            session.scalar(select(func.count()).select_from(TraceSpanORM)) or 0
        ) == 1

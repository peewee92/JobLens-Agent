"""SQLAlchemy Job Pool query behavior and SQL-shape tests."""
from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.application.job_queries import JobListQuery, JobSort
from app.db.base import Base
from app.db.models import JobORM, JobSourceORM
from app.domain.jobs import RemoteConfidence, RemoteStatus
from app.repositories import SqlAlchemyJobQueryRepository


@pytest.fixture
def query_environment(
    tmp_path: Path,
) -> Iterator[tuple[sessionmaker[Session], object]]:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'job-query.db'}")

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    seed_jobs(factory)
    yield factory, engine
    Base.metadata.drop_all(engine)
    engine.dispose()


def dt(day: int) -> datetime:
    return datetime(2026, 8, day, 8, 0, tzinfo=UTC)


def seed_jobs(factory: sessionmaker[Session]) -> None:
    with factory() as session:
        jobs = [
            JobORM(
                id="job_a",
                canonical_key="v1:a",
                title="AI 应用开发工程师",
                company="甲公司",
                area="武汉·光谷",
                salary_min_k=15,
                salary_max_k=30,
                experience="3-5年",
                education="本科",
                description="负责 Python Agent 平台",
                skills=["Python", "Agent"],
                remote_status=RemoteStatus.UNKNOWN,
                remote_confidence=RemoteConfidence.LOW,
            ),
            JobORM(
                id="job_b",
                canonical_key="v1:b",
                title="Senior Backend Engineer",
                company="Beta AI",
                area="武汉",
                salary_min_k=25,
                salary_max_k=40,
                description="FastAPI and distributed systems",
                skills=["Python", "FastAPI"],
                remote_status=RemoteStatus.CONFIRMED,
                remote_confidence=RemoteConfidence.HIGH,
            ),
            JobORM(
                id="job_c",
                canonical_key="v1:c",
                title="React 前端工程师",
                company="丙公司",
                area="上海",
                salary_min_k=10,
                salary_max_k=18,
                description="React desktop application",
                skills=["React"],
                remote_status=RemoteStatus.CONFIRMED,
                remote_confidence=RemoteConfidence.MEDIUM,
            ),
            JobORM(
                id="job_d",
                canonical_key="v1:d",
                title="数据工程师",
                company="丁公司",
                area="武汉",
                salary_min_k=None,
                salary_max_k=None,
                description=None,
                skills=[],
                remote_status=RemoteStatus.REJECTED,
                remote_confidence=RemoteConfidence.HIGH,
            ),
        ]
        session.add_all(jobs)
        session.flush()
        session.add_all(
            [
                JobSourceORM(
                    id="src_a_boss",
                    job_id="job_a",
                    source="boss",
                    source_job_id="a",
                    source_url="https://boss.example/a",
                    normalized_source_url="https://boss.example/a",
                    source_version="1.3.1",
                    source_raw={"source": "boss"},
                    first_seen_at=dt(1),
                    last_seen_at=dt(1),
                    collected_at=dt(1),
                ),
                JobSourceORM(
                    id="src_a_career",
                    job_id="job_a",
                    source="career-site",
                    source_job_id="a-career",
                    source_url="https://career.example/a",
                    normalized_source_url="https://career.example/a",
                    source_version="web-v1",
                    source_raw={"source": "career-site"},
                    first_seen_at=dt(2),
                    last_seen_at=dt(4),
                    collected_at=dt(4),
                ),
                JobSourceORM(
                    id="src_b",
                    job_id="job_b",
                    source="boss",
                    source_job_id="b",
                    source_url="https://boss.example/b",
                    normalized_source_url="https://boss.example/b",
                    source_version="1.3.1",
                    source_raw={},
                    first_seen_at=dt(2),
                    last_seen_at=dt(3),
                    collected_at=dt(3),
                ),
                JobSourceORM(
                    id="src_c",
                    job_id="job_c",
                    source="boss",
                    source_job_id="c",
                    source_url="https://boss.example/c",
                    normalized_source_url="https://boss.example/c",
                    source_version="1.3.1",
                    source_raw={},
                    first_seen_at=dt(1),
                    last_seen_at=dt(2),
                    collected_at=dt(2),
                ),
                JobSourceORM(
                    id="src_d",
                    job_id="job_d",
                    source="boss",
                    source_job_id="d",
                    source_url="https://boss.example/d",
                    normalized_source_url="https://boss.example/d",
                    source_version="1.3.1",
                    source_raw={},
                    first_seen_at=dt(1),
                    last_seen_at=dt(2),
                    collected_at=dt(2),
                ),
            ]
        )
        session.commit()


def test_list_filters_by_city_remote_keyword_salary_and_source(
    query_environment: tuple[sessionmaker[Session], object],
) -> None:
    factory, _engine = query_environment
    repository = SqlAlchemyJobQueryRepository(factory)

    page = repository.fetch_page(
        JobListQuery(
            q="backend",
            city="武汉",
            min_salary_k=20,
            remote_status=RemoteStatus.CONFIRMED,
            source="boss",
        )
    )

    assert page.total == 1
    assert [item.id for item in page.items] == ["job_b"]
    assert page.items[0].source == "boss"


def test_min_salary_uses_salary_max_and_excludes_unknown_salary(
    query_environment: tuple[sessionmaker[Session], object],
) -> None:
    factory, _engine = query_environment
    page = SqlAlchemyJobQueryRepository(factory).fetch_page(
        JobListQuery(min_salary_k=20, sort=JobSort.SALARY_ASC)
    )

    assert page.total == 2
    assert [item.id for item in page.items] == ["job_a", "job_b"]


def test_salary_sorting_is_stable_and_places_unknown_salary_last(
    query_environment: tuple[sessionmaker[Session], object],
) -> None:
    factory, _engine = query_environment
    repository = SqlAlchemyJobQueryRepository(factory)

    descending = repository.fetch_page(JobListQuery(sort=JobSort.SALARY_DESC))
    ascending = repository.fetch_page(JobListQuery(sort=JobSort.SALARY_ASC))

    assert [item.id for item in descending.items] == [
        "job_b",
        "job_a",
        "job_c",
        "job_d",
    ]
    assert [item.id for item in ascending.items] == [
        "job_c",
        "job_a",
        "job_b",
        "job_d",
    ]


def test_multiple_sources_produce_one_job_and_deterministic_primary_source(
    query_environment: tuple[sessionmaker[Session], object],
) -> None:
    factory, _engine = query_environment
    repository = SqlAlchemyJobQueryRepository(factory)

    unfiltered = repository.fetch_page(JobListQuery())
    boss_only = repository.fetch_page(JobListQuery(source="boss"))

    assert unfiltered.total == 4
    assert len({item.id for item in unfiltered.items}) == 4
    job_a = next(item for item in unfiltered.items if item.id == "job_a")
    assert job_a.source == "career-site"
    assert job_a.source_url == "https://career.example/a"

    boss_job_a = next(item for item in boss_only.items if item.id == "job_a")
    assert boss_job_a.source == "boss"
    assert boss_job_a.source_url == "https://boss.example/a"


def test_pagination_and_sorting_are_stable(
    query_environment: tuple[sessionmaker[Session], object],
) -> None:
    factory, _engine = query_environment
    repository = SqlAlchemyJobQueryRepository(factory)

    first = repository.fetch_page(JobListQuery(limit=2, offset=0))
    second = repository.fetch_page(JobListQuery(limit=2, offset=2))
    repeat = repository.fetch_page(JobListQuery(limit=2, offset=0))

    assert first.total == second.total == 4
    assert [item.id for item in first.items] == ["job_a", "job_b"]
    assert [item.id for item in second.items] == ["job_c", "job_d"]
    assert [item.id for item in repeat.items] == ["job_a", "job_b"]
    assert set(item.id for item in first.items).isdisjoint(
        item.id for item in second.items
    )


def test_detail_uses_latest_source_and_does_not_expose_storage_models(
    query_environment: tuple[sessionmaker[Session], object],
) -> None:
    factory, _engine = query_environment
    detail = SqlAlchemyJobQueryRepository(factory).get_job("job_a")

    assert detail is not None
    assert detail.id == "job_a"
    assert detail.skills == ("Python", "Agent")
    assert detail.description == "负责 Python Agent 平台"
    assert detail.source == "career-site"
    assert detail.source_url == "https://career.example/a"


def test_list_is_two_queries_and_detail_is_one_query(
    query_environment: tuple[sessionmaker[Session], object],
) -> None:
    factory, engine = query_environment
    repository = SqlAlchemyJobQueryRepository(factory)
    statements: list[str] = []

    @event.listens_for(engine, "before_cursor_execute")
    def _count_statements(
        _connection, _cursor, statement, _parameters, _context, _executemany
    ) -> None:
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    try:
        repository.fetch_page(JobListQuery())
        assert len(statements) == 2
        statements.clear()
        repository.get_job("job_a")
        assert len(statements) == 1
    finally:
        event.remove(engine, "before_cursor_execute", _count_statements)


def test_orphan_job_without_source_is_excluded_from_total_and_items(
    query_environment: tuple[sessionmaker[Session], object],
) -> None:
    factory, _engine = query_environment
    with factory() as session:
        session.add(
            JobORM(
                id="job_orphan",
                canonical_key="v1:orphan",
                title="Orphan",
                company="Broken Import",
                area="武汉",
                salary_min_k=10,
                salary_max_k=20,
                skills=[],
                remote_status=RemoteStatus.UNKNOWN,
                remote_confidence=RemoteConfidence.LOW,
            )
        )
        session.commit()

    page = SqlAlchemyJobQueryRepository(factory).fetch_page(JobListQuery())

    assert page.total == 4
    assert "job_orphan" not in {item.id for item in page.items}


def test_query_does_not_change_database_rows(
    query_environment: tuple[sessionmaker[Session], object],
) -> None:
    factory, _engine = query_environment
    repository = SqlAlchemyJobQueryRepository(factory)

    with factory() as session:
        before = (
            session.scalar(select(func.count()).select_from(JobORM)),
            session.scalar(select(func.count()).select_from(JobSourceORM)),
        )

    repository.fetch_page(JobListQuery())
    repository.get_job("job_a")

    with factory() as session:
        after = (
            session.scalar(select(func.count()).select_from(JobORM)),
            session.scalar(select(func.count()).select_from(JobSourceORM)),
        )
    assert after == before

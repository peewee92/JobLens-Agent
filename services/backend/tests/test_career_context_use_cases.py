"""Application and persistence evidence for Profile/SearchIntent versions."""
from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.application.career_context import (
    ContextVersionConflictError,
    EvidenceInput,
    InvalidCareerContextError,
    SaveProfileCommand,
    SaveSearchIntentCommand,
    SkillInput,
)
from app.application.career_context.use_cases import (
    GetProfileUseCase,
    GetSearchIntentUseCase,
    SaveProfileUseCase,
    SaveSearchIntentUseCase,
)
from app.db.base import Base
from app.db.models import (
    ProfileEvidenceORM,
    ProfileSkillEvidenceORM,
    ProfileSkillORM,
    SearchIntentORM,
    UserProfileORM,
)
from app.domain.career_context import EvidenceType, Seniority, SkillLevel
from app.repositories import (
    SqlAlchemyCareerContextQueryRepository,
    SqlAlchemyCareerContextUnitOfWork,
)


@pytest.fixture
def session_factory(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'career-context.db'}"
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


def profile_command(
    expected_version: int = 0,
    *,
    headline: str = "Frontend Engineer moving into AI applications",
) -> SaveProfileCommand:
    return SaveProfileCommand(
        expected_version=expected_version,
        headline=headline,
        years_of_experience=8,
        evidence=(
            EvidenceInput(
                key="spinach-desktop",
                type=EvidenceType.WORK,
                summary="Built Electron collaboration and Agent features.",
                source="confirmed by user",
            ),
            EvidenceInput(
                key="joblens",
                type=EvidenceType.PROJECT,
                summary="Built a FastAPI and Next.js evidence-based job system.",
                source="confirmed by user",
            ),
        ),
        skills=(
            SkillInput(
                name="React",
                level=SkillLevel.STRONG,
                evidence_keys=("spinach-desktop",),
            ),
            SkillInput(
                name="Agent Application Engineering",
                level=SkillLevel.WORKING,
                evidence_keys=("spinach-desktop", "joblens"),
            ),
        ),
    )


def intent_command(expected_version: int = 0) -> SaveSearchIntentCommand:
    return SaveSearchIntentCommand(
        expected_version=expected_version,
        target_roles=(" Agent Engineer ", "AI Application Engineer", "agent engineer"),
        cities=("武汉", " 武汉 "),
        remote_accepted=True,
        minimum_salary_k=20,
        seniority=Seniority.SENIOR,
        employment_types=("full_time", "full_time"),
        exclude_keywords=("博彩", " "),
        hard_constraints=("不接受长期驻场",),
        soft_preferences=("AI 产品有真实用户",),
    )


def count(session: Session, model: type) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


def make_profile_use_case(
    factory: sessionmaker[Session],
) -> SaveProfileUseCase:
    return SaveProfileUseCase(
        lambda: SqlAlchemyCareerContextUnitOfWork(factory)
    )


def make_intent_use_case(
    factory: sessionmaker[Session],
) -> SaveSearchIntentUseCase:
    return SaveSearchIntentUseCase(
        lambda: SqlAlchemyCareerContextUnitOfWork(factory)
    )


def test_profile_version_persists_relational_evidence_links(
    session_factory: sessionmaker[Session],
) -> None:
    result = make_profile_use_case(session_factory).execute(profile_command())

    assert result.version == 1
    assert result.id.startswith("prof_")
    assert len(result.evidence) == 2
    assert len(result.skills) == 2
    evidence_ids = {item.id for item in result.evidence}
    assert all(skill.evidence_ids for skill in result.skills)
    assert all(set(skill.evidence_ids) <= evidence_ids for skill in result.skills)

    with session_factory() as session:
        assert count(session, UserProfileORM) == 1
        assert count(session, ProfileEvidenceORM) == 2
        assert count(session, ProfileSkillORM) == 2
        assert count(session, ProfileSkillEvidenceORM) == 3


def test_profile_update_creates_new_version_and_preserves_history(
    session_factory: sessionmaker[Session],
) -> None:
    use_case = make_profile_use_case(session_factory)
    first = use_case.execute(profile_command())
    second = use_case.execute(
        profile_command(1, headline="AI Application Engineer with frontend depth")
    )

    assert first.version == 1
    assert second.version == 2
    assert first.id != second.id
    current = GetProfileUseCase(
        SqlAlchemyCareerContextQueryRepository(session_factory)
    ).execute()
    assert current.id == second.id
    assert current.headline == "AI Application Engineer with frontend depth"

    with session_factory() as session:
        versions = list(
            session.scalars(
                select(UserProfileORM.version).order_by(UserProfileORM.version)
            )
        )
        assert versions == [1, 2]
        assert count(session, ProfileEvidenceORM) == 4


def test_current_context_snapshot_returns_one_selected_latest_version_pair(
    session_factory: sessionmaker[Session],
) -> None:
    profile_use_case = make_profile_use_case(session_factory)
    intent_use_case = make_intent_use_case(session_factory)
    profile_use_case.execute(profile_command())
    intent_use_case.execute(intent_command())
    expected_profile = profile_use_case.execute(
        profile_command(1, headline="Confirmed Profile v2")
    )
    expected_intent = intent_use_case.execute(
        replace(intent_command(1), minimum_salary_k=25)
    )

    snapshot = SqlAlchemyCareerContextQueryRepository(
        session_factory
    ).get_current_context()

    assert snapshot.profile is not None
    assert snapshot.search_intent is not None
    assert snapshot.profile.id == expected_profile.id
    assert snapshot.profile.version == 2
    assert snapshot.search_intent.id == expected_intent.id
    assert snapshot.search_intent.version == 2


def test_profile_rejects_skill_without_evidence_and_writes_nothing(
    session_factory: sessionmaker[Session],
) -> None:
    command = profile_command()
    invalid = SaveProfileCommand(
        expected_version=0,
        headline=command.headline,
        years_of_experience=command.years_of_experience,
        evidence=command.evidence,
        skills=(
            SkillInput(
                name="Agent",
                level=SkillLevel.WORKING,
                evidence_keys=(),
            ),
        ),
    )

    with pytest.raises(InvalidCareerContextError, match="at least one evidence"):
        make_profile_use_case(session_factory).execute(invalid)

    with session_factory() as session:
        assert count(session, UserProfileORM) == 0
        assert count(session, ProfileEvidenceORM) == 0
        assert count(session, ProfileSkillORM) == 0


def test_profile_rejects_unknown_evidence_reference_and_writes_nothing(
    session_factory: sessionmaker[Session],
) -> None:
    command = profile_command()
    invalid = SaveProfileCommand(
        expected_version=0,
        headline=command.headline,
        years_of_experience=command.years_of_experience,
        evidence=command.evidence,
        skills=(
            SkillInput(
                name="Agent",
                level=SkillLevel.WORKING,
                evidence_keys=("invented-project",),
            ),
        ),
    )

    with pytest.raises(InvalidCareerContextError, match="unknown evidence"):
        make_profile_use_case(session_factory).execute(invalid)

    with session_factory() as session:
        assert count(session, UserProfileORM) == 0


def test_stale_profile_version_conflict_preserves_current_state(
    session_factory: sessionmaker[Session],
) -> None:
    use_case = make_profile_use_case(session_factory)
    first = use_case.execute(profile_command())

    with pytest.raises(ContextVersionConflictError, match="expected 0, current 1"):
        use_case.execute(profile_command(0, headline="stale edit"))

    with session_factory() as session:
        assert count(session, UserProfileORM) == 1
        assert session.get(UserProfileORM, first.id) is not None


def test_profile_transaction_rolls_back_complete_aggregate(
    session_factory: sessionmaker[Session],
) -> None:
    with pytest.raises(RuntimeError, match="simulated failure"):
        with SqlAlchemyCareerContextUnitOfWork(session_factory) as uow:
            uow.context.add_profile_version(profile_command(), version=1)
            raise RuntimeError("simulated failure")

    with session_factory() as session:
        assert count(session, UserProfileORM) == 0
        assert count(session, ProfileEvidenceORM) == 0
        assert count(session, ProfileSkillORM) == 0
        assert count(session, ProfileSkillEvidenceORM) == 0


def test_search_intent_versions_normalize_lists_and_preserve_history(
    session_factory: sessionmaker[Session],
) -> None:
    use_case = make_intent_use_case(session_factory)
    first = use_case.execute(intent_command())
    second = use_case.execute(
        replace(intent_command(1), minimum_salary_k=25)
    )

    assert first.target_roles == ("Agent Engineer", "AI Application Engineer")
    assert first.cities == ("武汉",)
    assert first.employment_types == ("full_time",)
    assert second.version == 2
    assert second.minimum_salary_k == 25
    current = GetSearchIntentUseCase(
        SqlAlchemyCareerContextQueryRepository(session_factory)
    ).execute()
    assert current.id == second.id

    with session_factory() as session:
        assert list(
            session.scalars(
                select(SearchIntentORM.version).order_by(SearchIntentORM.version)
            )
        ) == [1, 2]

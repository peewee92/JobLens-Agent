"""HTTP integration tests for Profile and SearchIntent confirmation."""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import (
    get_get_profile_use_case,
    get_get_search_intent_use_case,
    get_save_profile_use_case,
    get_save_search_intent_use_case,
)
from app.application.career_context.use_cases import (
    GetProfileUseCase,
    GetSearchIntentUseCase,
    SaveProfileUseCase,
    SaveSearchIntentUseCase,
)
from app.db.base import Base
from app.db.models import SearchIntentORM, UserProfileORM
from app.main import app
from app.repositories import (
    SqlAlchemyCareerContextQueryRepository,
    SqlAlchemyCareerContextUnitOfWork,
)


@pytest.fixture
def api_environment(tmp_path: Path) -> Iterator[tuple[TestClient, sessionmaker[Session]]]:
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'career-context-api.db'}"
    )

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    query_repository = SqlAlchemyCareerContextQueryRepository(factory)
    uow_factory = lambda: SqlAlchemyCareerContextUnitOfWork(factory)

    app.dependency_overrides[get_get_profile_use_case] = lambda: GetProfileUseCase(
        query_repository
    )
    app.dependency_overrides[get_save_profile_use_case] = lambda: SaveProfileUseCase(
        uow_factory
    )
    app.dependency_overrides[get_get_search_intent_use_case] = (
        lambda: GetSearchIntentUseCase(query_repository)
    )
    app.dependency_overrides[get_save_search_intent_use_case] = (
        lambda: SaveSearchIntentUseCase(uow_factory)
    )

    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client, factory
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def profile_payload(expected_version: int = 0) -> dict:
    return {
        "expectedVersion": expected_version,
        "headline": "Frontend Engineer moving into AI applications",
        "yearsOfExperience": 8,
        "evidence": [
            {
                "key": "spinach-desktop",
                "type": "work",
                "summary": "Built Electron collaboration and Agent features.",
                "source": "confirmed by user",
            },
            {
                "key": "joblens",
                "type": "project",
                "summary": "Built a FastAPI and Next.js job research product.",
                "source": "confirmed by user",
            },
        ],
        "skills": [
            {
                "name": "React",
                "level": "strong",
                "evidenceKeys": ["spinach-desktop"],
            },
            {
                "name": "Agent Application Engineering",
                "level": "working",
                "evidenceKeys": ["spinach-desktop", "joblens"],
            },
        ],
    }


def intent_payload(expected_version: int = 0) -> dict:
    return {
        "expectedVersion": expected_version,
        "targetRoles": [" Agent Engineer ", "AI Application Engineer", "agent engineer"],
        "cities": ["武汉", " 武汉 "],
        "remoteAccepted": True,
        "minimumSalaryK": 20,
        "seniority": "senior",
        "employmentTypes": ["full_time", "full_time"],
        "excludeKeywords": ["博彩"],
        "hardConstraints": ["不接受长期驻场"],
        "softPreferences": ["AI 产品有真实用户"],
    }


def test_empty_career_context_returns_structured_404(
    api_environment: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, _factory = api_environment

    profile = client.get("/api/v1/profile")
    intent = client.get("/api/v1/search-intent")

    assert profile.status_code == 404
    assert profile.json()["error"]["code"] == "profile_not_found"
    assert intent.status_code == 404
    assert intent.json()["error"]["code"] == "search_intent_not_found"


def test_profile_put_and_get_return_evidence_linked_public_contract(
    api_environment: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = api_environment

    created = client.put("/api/v1/profile", json=profile_payload())
    fetched = client.get("/api/v1/profile")

    assert created.status_code == 200
    assert fetched.status_code == 200
    body = fetched.json()
    assert body["version"] == 1
    assert body["id"].startswith("prof_")
    assert len(body["evidence"]) == 2
    assert len(body["skills"]) == 2
    evidence_ids = {item["id"] for item in body["evidence"]}
    assert all(item["evidenceIds"] for item in body["skills"])
    assert all(set(item["evidenceIds"]) <= evidence_ids for item in body["skills"])
    assert "preferences" not in body
    assert "profileKey" not in body

    with factory() as session:
        assert session.scalar(select(func.count(UserProfileORM.id))) == 1


def test_profile_stale_update_returns_409_and_creates_no_version(
    api_environment: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = api_environment
    assert client.put("/api/v1/profile", json=profile_payload()).status_code == 200

    stale = profile_payload(0)
    stale["headline"] = "stale overwrite"
    response = client.put("/api/v1/profile", json=stale)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "context_version_conflict"
    with factory() as session:
        assert session.scalar(select(func.count(UserProfileORM.id))) == 1


def test_profile_cross_field_violation_returns_422_and_creates_no_version(
    api_environment: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = api_environment
    payload = profile_payload()
    payload["skills"][0]["evidenceKeys"] = ["missing"]

    response = client.put("/api/v1/profile", json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_career_context"
    with factory() as session:
        assert session.scalar(select(func.count(UserProfileORM.id))) == 0


def test_search_intent_put_normalizes_and_versions_independently(
    api_environment: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = api_environment

    first = client.put("/api/v1/search-intent", json=intent_payload())
    second_payload = intent_payload(1)
    second_payload["minimumSalaryK"] = 25
    second = client.put("/api/v1/search-intent", json=second_payload)
    fetched = client.get("/api/v1/search-intent")

    assert first.status_code == 200
    assert second.status_code == 200
    assert fetched.status_code == 200
    body = fetched.json()
    assert body["version"] == 2
    assert body["targetRoles"] == ["Agent Engineer", "AI Application Engineer"]
    assert body["cities"] == ["武汉"]
    assert body["employmentTypes"] == ["full_time"]
    assert body["minimumSalaryK"] == 25
    assert "intentKey" not in body

    with factory() as session:
        assert session.scalar(select(func.count(SearchIntentORM.id))) == 2


def test_search_intent_stale_update_returns_409_and_creates_no_version(
    api_environment: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = api_environment
    assert (
        client.put("/api/v1/search-intent", json=intent_payload()).status_code
        == 200
    )

    stale = intent_payload(0)
    stale["minimumSalaryK"] = 30
    response = client.put("/api/v1/search-intent", json=stale)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "context_version_conflict"
    with factory() as session:
        assert session.scalar(select(func.count(SearchIntentORM.id))) == 1


def test_search_intent_rejects_roles_that_normalize_to_empty(
    api_environment: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = api_environment
    payload = intent_payload()
    payload["targetRoles"] = ["   "]

    response = client.put("/api/v1/search-intent", json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_career_context"
    with factory() as session:
        assert session.scalar(select(func.count(SearchIntentORM.id))) == 0


def test_openapi_contains_career_context_operations(
    api_environment: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, _factory = api_environment

    openapi = client.get("/openapi.json")

    assert openapi.status_code == 200
    paths = openapi.json()["paths"]
    assert paths["/api/v1/profile"]["get"]
    assert paths["/api/v1/profile"]["put"]
    assert paths["/api/v1/search-intent"]["get"]
    assert paths["/api/v1/search-intent"]["put"]

"""An empty database, user HTTP commands, existing workflows, no seeded reports."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from app.api import deps
from app.core.config import Settings
from app.db.base import Base
from app.main import app


@pytest.fixture
def first_user(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'first-user.db'}", connect_args={"check_same_thread": False})
    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(deps, "SessionLocal", factory)
    monkeypatch.setattr(deps, "engine", engine)
    monkeypatch.setattr(deps, "get_settings", lambda: Settings(_env_file=None,
        requirement_extractor_provider="fixture", semantic_match_provider="disabled", profile_extractor_provider="disabled"))
    with TestClient(app) as client:
        yield client, factory
    engine.dispose()


def save_inputs(client, supported=False):
    profile = client.put("/api/v1/profile", json={"expectedVersion": 0,
        "headline": "合成验收资料", "yearsOfExperience": 2,
        "evidence": [{"key": "project", "type": "project",
            "summary": "使用 Python 开发并维护服务" if supported else "编辑合成新闻通讯，整理采访记录",
            "source": "合成数据，不是真实职业经历"}],
        "skills": [{"name": "Python", "level": "working", "evidenceKeys": ["project"]}] if supported else []})
    assert profile.status_code == 200, profile.text
    intent = client.put("/api/v1/search-intent", json={"expectedVersion": 0, "targetRoles": ["后端工程师"],
        "cities": [], "remoteAccepted": None, "minimumSalaryK": None, "seniority": None,
        "employmentTypes": [], "excludeKeywords": [], "hardConstraints": [], "softPreferences": []})
    assert intent.status_code == 200, intent.text


def prepare_job(client, description):
    imported = client.post("/api/v1/job-imports/manual", json={"title": "后端工程师", "company": "合成验收公司", "description": description})
    assert imported.status_code == 201, imported.text
    job = imported.json()["jobId"]
    extracted = client.post(f"/api/v1/jobs/{job}/requirement-extractions")
    assert extracted.status_code == 201, extracted.text
    result = extracted.json()
    confirmation = client.post(f"/api/v1/jobs/{job}/requirement-confirmations", json={
        "actionId": "first-check", "extractionId": result["extractionId"], "inputHash": result["inputHash"],
        "factsDigest": result["factsDigest"], "confirmed": True})
    assert confirmation.status_code == 200, confirmation.text
    return job


@pytest.mark.parametrize("supported,description,expected", [
    (True, "任职要求：熟练掌握 Python，并能够以真实项目经历说明 Python 的工程应用、开发与维护能力。", "strong"),
    (False, "任职要求：熟练掌握 Python，并能够以真实项目经历说明 Python 的工程应用、开发与维护能力。", "low"),
    (False, "任职要求：至少5年以上工作经验，能够以真实的工作年限记录说明满足这一工作经验要求。", "blocked"),
])
def test_first_job_supported_unknown_and_hard_conflict(first_user, supported, description, expected):
    client, factory = first_user
    with factory() as session:
        for table in ("jobs", "user_profiles", "search_intents", "match_reports", "requirement_review_batch_final_decisions"):
            assert session.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 0
    save_inputs(client, supported)
    job = prepare_job(client, description)
    path = f"/api/v1/jobs/{job}"
    readiness = client.get(path + "/match-input-readiness").json()
    assert readiness["inputsReleaseEligible"], readiness
    response = client.post(path + "/match-report")
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["recommendation"] == expected, report
    assert report["providerCalls"] == 0
    history = client.get(path + "/match-reports").json()
    assert history["count"] == 1 and history["items"][0]["report"] == report
    assert history["items"][0]["isCurrent"]
    if supported:
        assert report["evidenceLinks"]
    else:
        assert not report["strengths"]
    if expected == "low":
        assert report["eligibility"] == "conditional"
    with factory() as session:
        assert session.execute(text("SELECT count(*) FROM requirement_review_batch_final_decisions")).scalar_one() == 0
        assert session.execute(text("SELECT count(*) FROM requirement_calls")).scalar_one() == 0
        assert session.execute(text("PRAGMA foreign_key_check")).all() == []

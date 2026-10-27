"""Saved analysis: real handlers/workflows/SQLite, not fabricated state trajectories."""
from dataclasses import asdict, replace
from datetime import datetime, UTC
from pathlib import Path
import importlib.util
from unittest.mock import Mock
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import sessionmaker

from app.api import deps
from app.application.saved_career_analysis import (
    AnalysisFactRequest, AnalysisJobBinding, PinnedAnalysisFacts, SavedCareerAnalysis,
    BuildSavedCareerAnalysisUseCase, AnalysisInputsBlockedError,
)
from app.application.job_preparation.bundle import BuildJobPreparationBundleUseCase
from app.application.target_cohort_gap_query import BuildSelectedFeedbackTargetCohortGapDetailsUseCase
from app.db.models import CareerAgentRunORM, UserProfileORM, SearchIntentORM, JobORM, JobRequirementExtractionORM, MatchReportORM
from app.main import app
from app.repositories.sqlalchemy_career_agent_checkpoint import SqlAlchemyCareerAgentCheckpointStore as Store
from .test_job_preparation_bundle import _profile, _extraction, _ready


@pytest.fixture
def synthetic_api(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("analysis_demo_seed", Path(__file__).parents[1] / "scripts/seed_mcp_demo.py")
    seed = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seed)
    database = tmp_path / "synthetic.db"
    ids = seed.seed(database)
    engine = create_engine(f"sqlite:///{database}", connect_args={"check_same_thread": False})
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(deps, "SessionLocal", factory)
    monkeypatch.setattr(deps, "engine", engine)
    with TestClient(app) as client:
        yield client, factory, ids
    engine.dispose()


def start(client, ids, thread="snapshot_thread"):
    response = client.post("/api/v1/career-agent/runs", json={
        "threadId": thread, "runId": f"run_{thread}", "requestId": f"req_{thread}", "jobIds": ids[:2], "topN": 2})
    assert response.status_code == 200, response.text
    state = response.json()
    assert state["status"] == "interrupted", state
    return state


def approve(client, state):
    return client.post(f"/api/v1/career-agent/runs/{state['threadId']}/resume", json={
        "interruptId": state["interruptId"], "actionId": "action_approve", "decision": "approve"})


def test_actual_production_dependency_saves_preparation_and_reopens_original_without_workflow(synthetic_api, monkeypatch):
    client, factory, ids = synthetic_api
    state = start(client, ids)
    completed = approve(client, state)
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "completed"
    assert completed.json()["resultId"]
    path = f"/api/v1/career-agent/runs/{state['threadId']}/result"
    first = client.get(path)
    assert first.status_code == 200, first.text
    result = first.json()
    assert result["isCurrent"] and result["schemaVersion"] == 1
    assert result["profileVersion"] == result["gaps"]["profileVersion"] == 1
    assert len(result["preparations"]) == 2
    assert all(item["factsUsable"] and item["profileVersion"] == 1 for item in result["preparations"])
    assert all(item["providerCalls"] == 0 for item in result["preparations"])
    for item in result["preparations"]:
        assert item["resumeDelta"]["highlights"]
        assert item["interviewFacts"]["items"][0]["evidenceIds"]
    history = Store(factory).load_history(thread_id=state["threadId"])
    monkeypatch.setattr(BuildSavedCareerAnalysisUseCase, "execute", Mock(side_effect=AssertionError("GET must not build")))
    monkeypatch.setattr(BuildJobPreparationBundleUseCase, "execute_from_facts", Mock(side_effect=AssertionError("GET must not prepare")))
    assert client.get(path).json() == result
    assert approve(client, state).json() == completed.json()
    assert Store(factory).load_history(thread_id=state["threadId"]) == history
    # A later confirmed Profile is a new fact, not a rewrite of old materials.
    with factory.begin() as session:
        session.add(UserProfileORM(id="profile_new", profile_key="default", version=2,
            headline="Synthetic later confirmed facts", years_of_experience=6))
    reopened = client.get(path).json()
    assert not reopened["isCurrent"] and "profile_changed" in reopened["staleReasons"]
    for key in ("resultId", "createdAt", "profileVersion", "gaps", "preparations", "bindings"):
        assert reopened[key] == result[key]


def test_nonempty_gap_mapping_roundtrips_and_all_layers_consume_the_same_pinned_facts():
    profile, extraction, ready = _profile(), _extraction(), _ready()
    request = AnalysisFactRequest(profile.id, profile.version, "intent", 1, ("report",), ("job_1",))
    facts = Mock()
    facts.capture.return_value = PinnedAnalysisFacts(profile,
        (AnalysisJobBinding("job_1", extraction.extraction_id, "report", "match-policy-v3", "Synthetic", "Demo"),),
        (extraction,), (ready,))
    unreadable = Mock(side_effect=AssertionError("must not load latest facts"))
    gaps = BuildSelectedFeedbackTargetCohortGapDetailsUseCase(cohort_creator=unreadable,
        requirement_aggregator=unreadable, profiles=unreadable)
    preparation = BuildJobPreparationBundleUseCase(readiness=unreadable, profiles=unreadable, requirements=unreadable)
    result = BuildSavedCareerAnalysisUseCase(facts=facts, gaps=gaps, preparation=preparation).execute(
        thread_id="thread", run_id="run", request=request)
    assert result.gaps.items  # Actual MappingProxyType from the real gap workflow.
    with pytest.raises(TypeError, match="mappingproxy"):
        asdict(result.gaps)  # Reproduce the old serialization failure before verifying the new boundary.
    serialized = json.loads(json.dumps(result.to_payload()))
    assert SavedCareerAnalysis.from_payload(serialized) == result
    from app.agent.graph.skill_gap_resume import _fingerprint
    assert _fingerprint(result.gaps) == _fingerprint(SavedCareerAnalysis.from_payload(serialized).gaps)
    assert result.gaps.profile_version == result.preparations[0].profile_version == profile.version
    preparation.execute_from_facts = Mock(return_value=replace(result.preparations[0], facts_usable=False))
    with pytest.raises(AnalysisInputsBlockedError):
        BuildSavedCareerAnalysisUseCase(facts=facts, gaps=gaps, preparation=preparation).execute(
            thread_id="thread", run_id="run", request=request)


def test_event_save_failure_rolls_back_result_then_continue_safely_recomputes(synthetic_api):
    client, factory, ids = synthetic_api
    state = start(client, ids, "rollback")
    with factory.begin() as session:
        session.execute(text("""CREATE TRIGGER fail_analysis_event BEFORE INSERT ON career_agent_run_events
            WHEN json_extract(NEW.payload, '$.status') = 'completed'
            BEGIN SELECT RAISE(ABORT, 'injected result save failure'); END"""))
    failure = approve(client, state)
    assert failure.status_code == 503, failure.text
    store = Store(factory)
    assert store.load_analysis(thread_id="rollback") is None
    before = store.load(thread_id="rollback")
    assert before.current_step == "skill_gap_ready" and before.result_id is None
    with factory.begin() as session:
        session.execute(text("DROP TRIGGER fail_analysis_event"))
    continued = client.post("/api/v1/career-agent/runs/rollback/continue")
    assert continued.status_code == 200, continued.text
    assert continued.json()["status"] == "completed"
    assert Store(factory).load_analysis(thread_id="rollback") is not None
    history = Store(factory).load_history(thread_id="rollback")
    assert sum(item.current_step == "target_cohort_resume" for item in history) == 1


@pytest.mark.parametrize("changed_fact", ["profile", "intent", "requirement", "match_report", "job_metadata"])
def test_facts_change_during_compute_keeps_historical_result_but_never_claims_current_completion(synthetic_api, monkeypatch, changed_fact):
    client, factory, ids = synthetic_api
    state = start(client, ids, "fact_race")
    original = BuildSavedCareerAnalysisUseCase.execute
    def compute_then_change(self, **kwargs):
        result = original(self, **kwargs)
        with factory.begin() as session:
            if changed_fact == "profile":
                session.add(UserProfileORM(id="new_during_compute", profile_key="default", version=2,
                    headline="Synthetic facts confirmed during compute", years_of_experience=6))
            elif changed_fact == "job_metadata":
                session.get(JobORM, ids[0]).area = "A different synthetic city"
            else:
                model = {"intent": SearchIntentORM, "requirement": JobRequirementExtractionORM,
                    "match_report": MatchReportORM}[changed_fact]
                statement = select(model)
                if changed_fact != "intent":
                    statement = statement.where(model.job_id == ids[0])
                old = session.scalars(statement).first()
                values = {attr.key: getattr(old, attr.key) for attr in inspect(model).column_attrs}
                values.update(id=f"new_{changed_fact}_during_compute", created_at=datetime.now(UTC))
                if changed_fact == "intent":
                    values["version"] += 1
                session.add(model(**values))
        return result
    monkeypatch.setattr(BuildSavedCareerAnalysisUseCase, "execute", compute_then_change)
    response = approve(client, state)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "stale" and response.json()["resultId"]
    saved = client.get("/api/v1/career-agent/runs/fact_race/result").json()
    assert saved["profileVersion"] == 1 and not saved["isCurrent"]
    assert all(item["profileVersion"] == 1 for item in saved["preparations"])


def test_old_completed_state_has_no_fabricated_snapshot(synthetic_api):
    client, factory, ids = synthetic_api
    state = start(client, ids, "not_saved_yet")
    assert approve(client, state).json()["status"] == "completed"
    # Simulate a pre-0025 primary completed row: fingerprint exists, full result does not.
    with factory.begin() as session:
        row = session.get(CareerAgentRunORM, "not_saved_yet")
        row.analysis_result = None
        payload = dict(row.payload)
        payload.pop("result_id", None)
        row.payload = payload
    response = client.get("/api/v1/career-agent/runs/not_saved_yet/result")
    assert response.status_code == 404
    assert Store(factory).load_analysis(thread_id="not_saved_yet") is None


def test_shared_saved_result_schema_is_exact():
    from app.api.v1.schemas.career_analysis import SavedCareerAnalysisResponse
    schema = json.loads((Path(__file__).parents[3] / "packages/contracts/schemas/career-agent-analysis-result.schema.json").read_text())
    schema.pop("$id"); schema.pop("$schema")
    assert schema == SavedCareerAnalysisResponse.model_json_schema(by_alias=True)
    from jsonschema import Draft202012Validator
    example = json.loads((Path(__file__).parents[3] / "packages/contracts/examples/career-agent-analysis-result.example.json").read_text())
    Draft202012Validator(schema).validate(example)

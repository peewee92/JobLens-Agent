"""Real SQLite transactions/concurrency; not synthetic final-state trajectories."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from hashlib import sha256
from threading import Barrier
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine, event, inspect, select
from sqlalchemy.orm import sessionmaker

from app.agent.graph.checkpoint import SQLiteCareerAgentCheckpointStore
from app.agent.graph.checkpoint_port import CheckpointConflictError, CheckpointNotReadyError
from app.agent.graph.hitl_decision import TargetCohortDecisionHandler, HumanDecisionRequest
from app.agent.graph.state import CareerAgentStatus as Status
from app.db.base import Base
from app.db.models import CareerAgentRunEventORM
from app.repositories.sqlalchemy_career_agent_checkpoint import SqlAlchemyCareerAgentCheckpointStore as Store
from .test_career_agent_hitl_decision import _interrupted_state


def _factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'primary.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def test_primary_restart_round_trip_and_append_events_without_payload_dedup(tmp_path):
    factory = _factory(tmp_path)
    store = Store(factory)
    running = replace(_interrupted_state(), status=Status.RUNNING, current_step="rank_jobs", pending_approval=False)
    current = store.transition(None, running)
    first = store.transition(current, current)
    second = store.transition(first, first)
    assert [item.revision for item in store.load_history(thread_id=current.thread_id)] == [0, 1, 2]
    assert Store(factory).load(thread_id=current.thread_id) == second
    assert not hasattr(store, "save")


def test_two_real_decisions_compete_for_one_revision_only_one_can_commit(tmp_path):
    factory = _factory(tmp_path)
    store = Store(factory)
    original = store.transition(None, _interrupted_state())
    barrier = Barrier(2)
    class CompetingStore(Store):
        def transition(self, previous, candidate):
            if previous is not None and previous.status is Status.INTERRUPTED:
                barrier.wait(timeout=5)
            return super().transition(previous, candidate)
    def decide(decision):
        handler = TargetCohortDecisionHandler(checkpoints=CompetingStore(factory))
        try:
            return handler.submit(HumanDecisionRequest(thread_id=original.thread_id,
                interrupt_id=original.interrupt_id, action_id=f"action_{decision}", decision=decision))
        except CheckpointConflictError:
            return "conflict"
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(decide, ["approve", "reject"]))
    assert results.count("conflict") == 1
    winner = next(item for item in results if item != "conflict")
    assert store.load(thread_id=original.thread_id) == winner
    assert winner.revision == 1
    assert len(store.load_history(thread_id=original.thread_id)) == 2


def test_event_save_failure_rolls_back_state_then_retry_can_commit(tmp_path):
    factory = _factory(tmp_path)
    store = Store(factory)
    current = store.transition(None, _interrupted_state())
    candidate = replace(current, status=Status.CANCELLED, current_step="target_cohort_rejected", pending_approval=False)
    def fail_event(_conn, _cursor, sql, *_):
        if sql.startswith("INSERT INTO career_agent_run_events"):
            raise RuntimeError("injected event save failure")
    event.listen(factory.kw["bind"], "before_cursor_execute", fail_event)
    try:
        with pytest.raises(RuntimeError, match="injected"):
            store.transition(current, candidate)
    finally:
        event.remove(factory.kw["bind"], "before_cursor_execute", fail_event)
    assert store.load(thread_id=current.thread_id) == current
    assert store.load_history(thread_id=current.thread_id) == (current,)
    assert store.transition(current, candidate).revision == 1


def test_missing_schema_is_read_only_and_requires_migration(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'not-migrated.db'}")
    with pytest.raises(CheckpointNotReadyError):
        Store(sessionmaker(bind=engine))
    assert not (tmp_path / "not-migrated.db").exists()
    assert inspect(engine).get_table_names() == []


@pytest.mark.parametrize("status, step", [(Status.INTERRUPTED, "legacy_reanalysis_required"), (Status.COMPLETED, "legacy_completed_no_snapshot")])
def test_old_checkpoint_file_is_read_only_never_silently_resumed(tmp_path, status, step):
    legacy_path = tmp_path / "old.db"
    legacy = SQLiteCareerAgentCheckpointStore(legacy_path)
    legacy.save(replace(_interrupted_state(), status=status))
    before = sha256(legacy_path.read_bytes()).hexdigest()
    store = Store(_factory(tmp_path), legacy_path=legacy_path)
    loaded = store.load(thread_id="thread_1")
    assert loaded.legacy_read_only and loaded.current_step == step
    assert loaded.status is (Status.STALE if status is Status.INTERRUPTED else Status.COMPLETED)
    with pytest.raises(CheckpointConflictError):
        store.transition(loaded, replace(loaded, status=Status.RESUMING, current_step="target_cohort_resume"))
    with pytest.raises(CheckpointConflictError):
        store.transition(None, _interrupted_state())
    assert sha256(legacy_path.read_bytes()).hexdigest() == before
    with store._factory() as session:
        assert session.scalars(select(CareerAgentRunEventORM)).all() == []


def test_production_dependency_uses_primary_store_and_does_not_create_legacy_file(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from app.api import deps
    factory = _factory(tmp_path)
    legacy = tmp_path / "absent-legacy.db"
    monkeypatch.setattr(deps, "SessionLocal", factory)
    monkeypatch.setattr(deps, "get_settings", lambda: SimpleNamespace(career_agent_checkpoint_path=legacy))
    service = deps.get_career_agent_hitl_service(career_context=Mock(), jobs=Mock(), ranking=Mock(),
        target_cohort_gaps=Mock(), job_preparation=Mock())
    assert isinstance(service._checkpoints, Store)
    assert service.get_state(thread_id="not-there") is None
    assert not legacy.exists()


@pytest.mark.parametrize("mutation", [
    {"run_id": "other"}, {"profile_version": 999}, {"current_match_report_ids": ("other",)},
    {"current_step": "unknown", "status": Status.RESUMING},
    {"current_step": "skill_gap_completed", "status": Status.COMPLETED},
])
def test_illegal_state_changes_do_not_append_events(tmp_path, mutation):
    store = Store(_factory(tmp_path))
    current = store.transition(None, _interrupted_state())
    with pytest.raises(CheckpointConflictError):
        store.transition(current, replace(current, **mutation))
    assert store.load_history(thread_id=current.thread_id) == (current,)


def test_storage_errors_are_actionable_http_responses_and_get_has_no_execution(tmp_path):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.api.deps import get_career_agent_hitl_service
    def unavailable():
        raise CheckpointNotReadyError("运行存储需要迁移")
    app.dependency_overrides[get_career_agent_hitl_service] = unavailable
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/career-agent/runs/any")
            assert response.status_code == 503
            assert response.json()["error"]["code"] == "career_agent_storage_not_ready"
        service = Mock()
        service.resume.side_effect = CheckpointConflictError("修订已改变")
        app.dependency_overrides[get_career_agent_hitl_service] = lambda: service
        with TestClient(app) as client:
            response = client.post("/api/v1/career-agent/runs/any/resume", json={
                "interruptId": "i", "actionId": "a", "decision": "approve"})
            assert response.status_code == 409
            assert response.json()["error"]["code"] == "career_agent_state_conflict"
    finally:
        app.dependency_overrides.pop(get_career_agent_hitl_service, None)

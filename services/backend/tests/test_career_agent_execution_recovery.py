"""Actual SQLite leases, fenced writes, crash points and explicit HTTP continue."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select

from app.agent.graph.checkpoint_port import CheckpointConflictError
from app.agent.graph.hitl_service import StartCareerAgentRunRequest, ResumeCareerAgentRunRequest
from app.agent.graph.state import CareerAgentStatus as Status
from app.api.deps import get_career_agent_hitl_service
from app.db.models import CareerAgentRunORM
from app.main import app
from app.repositories.sqlalchemy_career_agent_checkpoint import SqlAlchemyCareerAgentCheckpointStore as Store
from .test_career_agent_primary_store import _factory
from .test_career_agent_hitl_decision import _interrupted_state
from .test_career_agent_command_integrity import _service
from .test_career_agent_rank_interrupt_graph import _RankingWorkflow, _stored


def test_only_one_concurrent_executor_can_claim_real_sqlite(tmp_path):
    factory = _factory(tmp_path)
    state = Store(factory).transition(None, _interrupted_state())
    started, acquired = Barrier(2), Barrier(2)
    def execute(_):
        started.wait(timeout=5)
        try:
            with Store(factory).execution(thread_id=state.thread_id):
                acquired.wait(timeout=5)
                return "claimed"
        except CheckpointConflictError:
            acquired.wait(timeout=5)
            return "conflict"
    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(execute, range(2))) == ["claimed", "conflict"]
    assert Store(factory).load_history(thread_id=state.thread_id) == (state,)


def test_expired_writer_cannot_start_more_work_commit_or_release_new_claim(tmp_path):
    factory = _factory(tmp_path)
    now = [100.0]
    store = Store(factory, clock=lambda: now[0])
    state = store.transition(None, _interrupted_state())
    candidate = replace(state, status=Status.CANCELLED, current_step="target_cohort_rejected", pending_approval=False)
    first = store.execution(thread_id=state.thread_id, lease_seconds=10)
    old_writer = first.__enter__()
    with pytest.raises(CheckpointConflictError):
        store.transition(state, candidate)  # Unclaimed writes cannot bypass a live lease.
    now[0] = 111
    with store.execution(thread_id=state.thread_id) as new_writer:
        with pytest.raises(CheckpointConflictError):
            old_writer.assert_execution()
        with pytest.raises(CheckpointConflictError):
            old_writer.transition(state, candidate)
        first.__exit__(None, None, None)  # Must not release the new writer's token.
        new_writer.assert_execution()
        accepted = new_writer.transition(state, candidate)
    assert store.load(thread_id=state.thread_id) == accepted
    with factory() as session:
        row = session.get(CareerAgentRunORM, state.thread_id)
        assert row.lease_token is None and row.lease_expires_at is None


def _ranking():
    return _RankingWorkflow((_stored("mr_1", "job_1"), _stored("mr_2", "job_2")), [])


def _request():
    return StartCareerAgentRunRequest("thread", "run", "request", ("job_1", "job_2"), 2)


@pytest.mark.parametrize("crash_at", ["ranking", "interrupt"])
def test_restart_continue_recovers_saved_input_or_saved_ranking_without_implicit_get_execution(tmp_path, crash_at):
    factory = _factory(tmp_path)
    ranking = _ranking()
    def fail_once(_conn, _cursor, sql, params, *_):
        if crash_at == "interrupt" and sql.startswith("UPDATE career_agent_runs") and "interrupted" in params:
            raise RuntimeError("injected waiting point save failure")
    if crash_at == "ranking":
        original_execute = ranking.execute
        ranking.execute = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("injected ranking failure"))
    else:
        event.listen(factory.kw["bind"], "before_cursor_execute", fail_once)
    try:
        with pytest.raises(RuntimeError, match="injected"):
            _service(factory, ranking).start(_request())
    finally:
        if crash_at == "ranking":
            ranking.execute = original_execute
        else:
            event.remove(factory.kw["bind"], "before_cursor_execute", fail_once)
    before = Store(factory).load(thread_id="thread")
    assert before.status is (Status.CREATED if crash_at == "ranking" else Status.RUNNING)
    history = Store(factory).load_history(thread_id="thread")
    # A fresh application service is built per HTTP request, like a restarted process.
    app.dependency_overrides[get_career_agent_hitl_service] = lambda: _service(factory, ranking)
    try:
        with TestClient(app) as client:
            assert client.get("/api/v1/career-agent/runs/thread").json()["status"] == before.status.value
            assert Store(factory).load_history(thread_id="thread") == history
            response = client.post("/api/v1/career-agent/runs/thread/continue")
            assert response.status_code == 200
            assert response.json()["status"] == "interrupted"
            assert response.json()["proposedTargetJobIds"] == ["job_1", "job_2"]
            assert response.json()["revision"] == 2
            assert client.post("/api/v1/career-agent/runs/thread/continue").json() == response.json()
    finally:
        app.dependency_overrides.pop(get_career_agent_hitl_service, None)
    assert len(ranking.calls) == 1  # Saved ranking is reused, not recalculated.
    assert len(Store(factory).load_history(thread_id="thread")) == 3


def test_created_run_with_changed_facts_is_marked_stale_not_rebound(tmp_path):
    factory = _factory(tmp_path)
    state = replace(_interrupted_state(), thread_id="old", status=Status.CREATED,
        current_step="analysis_created", profile_version=999, pending_approval=False)
    Store(factory).transition(None, state)
    ranking = _ranking()
    result = _service(factory, ranking).continue_run(thread_id="old")
    assert result.status is Status.STALE
    assert result.profile_version == 999
    assert ranking.calls == []


def test_accepted_decision_survives_workflow_failure_and_continue_does_not_reconsume(tmp_path):
    from unittest.mock import Mock
    from app.agent.graph.hitl_service import CareerAgentHitlService
    from app.agent.tool_registry import CareerAgentToolRegistry
    from .test_career_agent_hitl_recovery import _GapWorkflow
    from .test_career_agent_rank_interrupt_graph import _context, _UnusedWorkflow
    factory = _factory(tmp_path)
    ranking = _ranking()
    gaps = _GapWorkflow()
    registry = CareerAgentToolRegistry(ranking=ranking, target_cohort_gaps=gaps, job_preparation=_UnusedWorkflow())
    builder = Mock()
    builder.build.return_value = _context()
    def service():
        return CareerAgentHitlService(checkpoints=Store(factory), context_builder=builder, tool_registry=registry)
    started = service().start(_request())
    original_execute = gaps.execute
    gaps.execute = lambda *_: (_ for _ in ()).throw(RuntimeError("injected gap failure"))
    with pytest.raises(RuntimeError, match="injected"):
        service().resume(ResumeCareerAgentRunRequest("thread", started.interrupt_id, "action", "approve"))
    gaps.execute = original_execute
    saved = Store(factory).load(thread_id="thread")
    assert saved.status is Status.RESUMING and saved.current_step == "skill_gap_ready"
    app.dependency_overrides[get_career_agent_hitl_service] = service
    try:
        with TestClient(app) as client:
            assert client.get("/api/v1/career-agent/runs/thread").json()["status"] == "resuming"
            assert gaps.calls == 0
            completed = client.post("/api/v1/career-agent/runs/thread/continue")
            assert completed.status_code == 200 and completed.json()["status"] == "completed"
            assert client.post("/api/v1/career-agent/runs/thread/continue").json() == completed.json()
    finally:
        app.dependency_overrides.pop(get_career_agent_hitl_service, None)
    assert gaps.calls == 1
    final = Store(factory).load(thread_id="thread")
    assert final.decision_action_id == "action" and final.decision_command_digest == saved.decision_command_digest
    assert [state.status for state in Store(factory).load_history(thread_id="thread")].count(Status.INTERRUPTED) == 1


def test_explicit_continue_cannot_run_under_another_live_executor(tmp_path):
    factory = _factory(tmp_path)
    ranking = _ranking()
    state = _service(factory, ranking).start(_request())
    # Pretend a prior request saved ranking and is still working on the wait point.
    # A separate initial run lets us keep normal transition rules intact.
    created = replace(_interrupted_state(), thread_id="pending", status=Status.CREATED,
                      current_step="analysis_created", pending_approval=False)
    store = Store(factory)
    store.transition(None, created)
    with store.execution(thread_id="pending"):
        with pytest.raises(CheckpointConflictError):
            _service(factory, ranking).continue_run(thread_id="pending")
    assert len(ranking.calls) == 1
    assert Store(factory).load(thread_id="pending").status is Status.CREATED


def test_event_constraint_failure_is_save_error_not_a_fabricated_concurrent_update(tmp_path):
    from sqlalchemy import text
    from app.agent.graph.checkpoint_port import CheckpointPersistenceError
    factory = _factory(tmp_path)
    store = Store(factory)
    current = store.transition(None, _interrupted_state())
    with factory() as session, session.begin():
        session.execute(text("""CREATE TRIGGER fail_event BEFORE INSERT ON career_agent_run_events
            BEGIN SELECT RAISE(ABORT, 'injected persistence failure'); END"""))
    with pytest.raises(CheckpointPersistenceError):
        store.transition(current, replace(current, status=Status.CANCELLED,
            current_step="target_cohort_rejected", pending_approval=False))
    assert store.load(thread_id=current.thread_id) == current
    assert len(store.load_history(thread_id=current.thread_id)) == 1
    service = _service(factory, _ranking())
    app.dependency_overrides[get_career_agent_hitl_service] = lambda: service
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/career-agent/runs/thread_1/resume", json={
                "interruptId": current.interrupt_id, "actionId": "test", "decision": "reject"})
            assert response.status_code == 503
            assert response.json()["error"]["code"] == "career_agent_save_failed"
            assert "injected persistence failure" not in response.text
    finally:
        app.dependency_overrides.pop(get_career_agent_hitl_service, None)

"""Command content replay against the real primary SQLite store and actual graph."""
from dataclasses import replace
from unittest.mock import Mock

import pytest

from app.agent.graph.checkpoint_port import CheckpointConflictError
from app.agent.graph.hitl_decision import (
    HumanDecisionConflictError, HumanDecisionRequest, TargetCohortDecisionHandler,
)
from app.agent.graph.hitl_service import CareerAgentHitlService, StartCareerAgentRunRequest
from app.agent.tool_registry import CareerAgentToolRegistry
from app.repositories.sqlalchemy_career_agent_checkpoint import SqlAlchemyCareerAgentCheckpointStore as Store
from .test_career_agent_primary_store import _factory
from .test_career_agent_hitl_decision import _interrupted_state
from .test_career_agent_rank_interrupt_graph import _context, _stored, _RankingWorkflow, _UnusedWorkflow


def _service(factory, ranking):
    builder = Mock()
    builder.build.return_value = _context()
    registry = CareerAgentToolRegistry(ranking=ranking, target_cohort_gaps=_UnusedWorkflow(),
                                      job_preparation=_UnusedWorkflow())
    return CareerAgentHitlService(checkpoints=Store(factory), context_builder=builder, tool_registry=registry)


def test_start_content_replay_survives_service_restart_and_never_reexecutes(tmp_path):
    factory = _factory(tmp_path)
    ranking = _RankingWorkflow((_stored("mr_1", "job_1"), _stored("mr_2", "job_2")), [])
    request = StartCareerAgentRunRequest("thread_1", "run_1", "request_1", ("job_1", "job_2"), 2)
    result = _service(factory, ranking).start(request)
    assert result.start_command_digest and len(result.start_command_digest) == 64
    service = _service(factory, ranking)
    assert service.start(request) == result
    assert service.start(replace(request, job_ids=("job_1", "job_1", "job_2"))) == result
    for different in (replace(request, top_n=1), replace(request, job_ids=("job_1",)),
                      replace(request, job_ids=("job_2", "job_1"))):
        with pytest.raises(CheckpointConflictError):
            service.start(different)
    assert len(ranking.calls) == 1
    assert len(Store(factory).load_history(thread_id="thread_1")) == 3


@pytest.mark.parametrize("decision", ["approve", "edit", "reject"])
def test_decision_content_replay_is_durable_and_changed_content_conflicts(tmp_path, decision):
    factory = _factory(tmp_path)
    store = Store(factory)
    state = store.transition(None, _interrupted_state())
    request = HumanDecisionRequest(state.thread_id, state.interrupt_id, "action_1", decision,
                                   ("job_2", "job_1") if decision == "edit" else ())
    accepted = TargetCohortDecisionHandler(checkpoints=store).submit(request)
    handler = TargetCohortDecisionHandler(checkpoints=Store(factory))
    assert handler.submit(request) == accepted
    if decision == "edit":
        assert handler.submit(replace(request, selected_job_ids=("job_2", "job_1", "job_2"))) == accepted
    for different in (replace(request, interrupt_id="different"),
                      replace(request, selected_job_ids=("job_3",)),
                      replace(request, decision="reject" if decision != "reject" else "approve")):
        with pytest.raises(HumanDecisionConflictError):
            handler.submit(different)
    assert len(store.load_history(thread_id=state.thread_id)) == 2
    assert Store(factory).load(thread_id=state.thread_id) == accepted


def test_accepted_digest_and_decision_are_immutable(tmp_path):
    store = Store(_factory(tmp_path))
    state = store.transition(None, replace(_interrupted_state(), start_command_digest="original"))
    with pytest.raises(CheckpointConflictError):
        store.transition(state, replace(state, start_command_digest="changed"))
    handler = TargetCohortDecisionHandler(checkpoints=store)
    accepted = handler.submit(HumanDecisionRequest(state.thread_id, state.interrupt_id, "action", "approve"))
    for mutation in ({"decision_command_digest": "changed"}, {"decision_action_id": "other"},
                     {"confirmed_target_job_ids": ("job_3",)}, {"human_decision": "edit"}):
        with pytest.raises(CheckpointConflictError):
            store.transition(accepted, replace(accepted, **mutation))
    assert len(store.load_history(thread_id=state.thread_id)) == 2


def test_old_accepted_command_without_digest_fails_closed_not_silently_replayed(tmp_path):
    factory = _factory(tmp_path)
    store = Store(factory)
    state = store.transition(None, _interrupted_state())
    ranking = _RankingWorkflow((), [])
    with pytest.raises(CheckpointConflictError, match="旧运行"):
        _service(factory, ranking).start(StartCareerAgentRunRequest(
            state.thread_id, state.run_id, state.request_id, state.requested_job_ids))
    # Old persisted decisions have no digest; they remain readable, not verifiably replayable.
    from app.agent.graph.state import CareerAgentStatus
    old = store.transition(state, replace(state, status=CareerAgentStatus.RESUMING,
        current_step="target_cohort_resume", pending_approval=False,
        decision_action_id="old", human_decision="approve"))
    with pytest.raises(HumanDecisionConflictError, match="旧决定"):
        TargetCohortDecisionHandler(checkpoints=store).submit(
            HumanDecisionRequest(state.thread_id, state.interrupt_id, "old", "approve"))
    assert store.load(thread_id=state.thread_id) == old
    assert ranking.calls == []


def test_http_changed_command_cannot_mutate_original_run_or_decision(tmp_path):
    from fastapi.testclient import TestClient
    from app.api.deps import get_career_agent_hitl_service
    from app.main import app
    factory = _factory(tmp_path)
    ranking = _RankingWorkflow((_stored("mr_1", "job_1"), _stored("mr_2", "job_2")), [])
    app.dependency_overrides[get_career_agent_hitl_service] = lambda: _service(factory, ranking)
    try:
        with TestClient(app) as client:
            body = {"threadId": "http", "runId": "run", "requestId": "request",
                    "jobIds": ["job_1", "job_2"], "topN": 1}
            original = client.post("/api/v1/career-agent/runs", json=body)
            assert original.status_code == 200
            assert "startCommandDigest" not in original.json()
            assert client.post("/api/v1/career-agent/runs", json=body).json() == original.json()
            conflict = client.post("/api/v1/career-agent/runs", json={**body, "topN": 2})
            assert conflict.status_code == 409
            assert conflict.json()["error"]["code"] == "career_agent_state_conflict"
            decision = {"interruptId": original.json()["interruptId"],
                        "actionId": "http-action", "decision": "reject"}
            accepted = client.post("/api/v1/career-agent/runs/http/resume", json=decision)
            assert accepted.status_code == 200
            assert accepted.json()["status"] == "cancelled"
            assert client.post("/api/v1/career-agent/runs/http/resume", json=decision).json() == accepted.json()
            for changed in ({**decision, "decision": "approve"}, {**decision, "interruptId": "wrong"}):
                assert client.post("/api/v1/career-agent/runs/http/resume", json=changed).status_code == 409
            assert client.get("/api/v1/career-agent/runs/http").json() == accepted.json()
            assert len(Store(factory).load_history(thread_id="http")) == 4
            assert len(ranking.calls) == 1
    finally:
        app.dependency_overrides.pop(get_career_agent_hitl_service, None)

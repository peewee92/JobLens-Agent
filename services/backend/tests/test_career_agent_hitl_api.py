from dataclasses import replace

from fastapi.testclient import TestClient

from app.agent.graph.hitl_decision import HumanDecisionValidationError
from app.agent.graph.state import CareerAgentState, CareerAgentStatus
from app.api.deps import get_career_agent_hitl_service
from app.main import app


_INTERRUPTED = CareerAgentState(
    thread_id="thread-1",
    run_id="run-1",
    request_id="request-1",
    status=CareerAgentStatus.INTERRUPTED,
    current_step="target_cohort_confirmation",
    goal="analyze_target_cohort_gaps",
    profile_id="profile-1",
    profile_version=1,
    search_intent_id="intent-1",
    search_intent_version=1,
    requested_job_ids=("job-1", "job-2"),
    ranked_job_ids=("job-1", "job-2"),
    proposed_target_job_ids=("job-1",),
    current_match_report_ids=("report-1", "report-2"),
    match_fingerprint="fingerprint",
    pending_approval=True,
    interrupt_id="interrupt-1",
)


class _HitlService:
    def __init__(self) -> None:
        self.state = _INTERRUPTED
        self.started_with = None
        self.resumed_with = None

    def start(self, request):
        self.started_with = request
        return self.state

    def get_state(self, *, thread_id: str):
        return self.state if thread_id == self.state.thread_id else None

    def resume(self, request):
        self.resumed_with = request
        if request.interrupt_id == "wrong":
            raise HumanDecisionValidationError("interrupt_id does not match pending interrupt")
        if request.decision == "reject":
            self.state = replace(
                self.state,
                status=CareerAgentStatus.CANCELLED,
                current_step="target_cohort_rejected",
                pending_approval=False,
                human_decision="reject",
                decision_action_id=request.action_id,
            )
        else:
            self.state = replace(
                self.state,
                status=CareerAgentStatus.COMPLETED,
                current_step="skill_gap_completed",
                pending_approval=False,
                human_decision=request.decision,
                decision_action_id=request.action_id,
                confirmed_target_job_ids=self.state.proposed_target_job_ids,
                gap_result_fingerprint="gap-fingerprint",
            )
        return self.state


def test_hitl_run_state_and_resume_are_exposed_as_one_durable_api_seam() -> None:
    service = _HitlService()
    app.dependency_overrides[get_career_agent_hitl_service] = lambda: service
    try:
        with TestClient(app) as client:
            started = client.post(
                "/api/v1/career-agent/runs",
                json={
                    "threadId": "thread-1",
                    "runId": "run-1",
                    "requestId": "request-1",
                    "jobIds": ["job-1", "job-2"],
                    "topN": 1,
                },
            )
            loaded = client.get("/api/v1/career-agent/runs/thread-1")
            resumed = client.post(
                "/api/v1/career-agent/runs/thread-1/resume",
                json={
                    "interruptId": "interrupt-1",
                    "actionId": "action-1",
                    "decision": "approve",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert started.status_code == 200
    assert started.json()["status"] == "interrupted"
    assert started.json()["interruptId"] == "interrupt-1"
    assert loaded.status_code == 200
    assert loaded.json()["proposedTargetJobIds"] == ["job-1"]
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "completed"
    assert resumed.json()["currentStep"] == "skill_gap_completed"
    assert service.started_with.job_ids == ("job-1", "job-2")
    assert service.resumed_with.thread_id == "thread-1"


def test_hitl_resume_validation_error_is_fail_closed() -> None:
    service = _HitlService()
    app.dependency_overrides[get_career_agent_hitl_service] = lambda: service
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/career-agent/runs/thread-1/resume",
                json={
                    "interruptId": "wrong",
                    "actionId": "action-1",
                    "decision": "approve",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert "interrupt_id" in response.json()["detail"]


def test_hitl_missing_thread_returns_404() -> None:
    service = _HitlService()
    app.dependency_overrides[get_career_agent_hitl_service] = lambda: service
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/career-agent/runs/missing")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404


def test_openapi_registers_durable_career_agent_run_contracts() -> None:
    with TestClient(app) as client:
        paths = client.get("/openapi.json").json()["paths"]

    assert "/api/v1/career-agent/runs" in paths
    assert "/api/v1/career-agent/runs/{thread_id}" in paths
    assert "/api/v1/career-agent/runs/{thread_id}/resume" in paths

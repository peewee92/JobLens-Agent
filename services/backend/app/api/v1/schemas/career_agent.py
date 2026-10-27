from pydantic import Field, ConfigDict

from typing import Literal

from app.agent.entrypoint import CareerAgentGoal, CareerAgentTurn
from app.agent.graph.hitl_service import (
    ResumeCareerAgentRunRequest,
    StartCareerAgentRunRequest,
)
from app.agent.graph.state import CareerAgentState, CareerAgentStatus
from app.api.v1.schemas.common import CamelCaseModel


class CareerAgentTurnRequest(CamelCaseModel):
    goal: CareerAgentGoal
    current_job_id: str | None = None
    relevant_evidence_ids: list[str] = Field(default_factory=list)
    job_ids: list[str] = Field(default_factory=list)
    include_blocked: bool = False
    top_n: int | None = Field(default=None, ge=1, le=50)
    cohort_id: str | None = None
    cohort_name: str | None = None
    selected_feedback_ids: list[str] = Field(default_factory=list)

    def to_command(self) -> CareerAgentTurn:
        return CareerAgentTurn(
            goal=self.goal,
            current_job_id=self.current_job_id,
            relevant_evidence_ids=tuple(self.relevant_evidence_ids),
            job_ids=tuple(self.job_ids),
            include_blocked=self.include_blocked,
            top_n=self.top_n,
            cohort_id=self.cohort_id,
            cohort_name=self.cohort_name,
            selected_feedback_ids=tuple(self.selected_feedback_ids),
        )


class CareerAgentRunRequest(CamelCaseModel):
    thread_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    request_id: str = Field(min_length=1)
    job_ids: list[str] = Field(min_length=1, max_length=50)
    top_n: int = Field(default=3, ge=1, le=5)

    def to_command(self) -> StartCareerAgentRunRequest:
        return StartCareerAgentRunRequest(
            thread_id=self.thread_id,
            run_id=self.run_id,
            request_id=self.request_id,
            job_ids=tuple(self.job_ids),
            top_n=self.top_n,
        )


class UpdateMatchStepResponse(CamelCaseModel):
    job_id: str
    extraction_id: str | None
    status: Literal["pending", "running", "completed", "reused", "failed", "requires_model", "input_blocked"]
    report_id: str | None
    attempt: int
    error_code: str | None


class ContinueAnalysisRequest(CamelCaseModel):
    model_config = ConfigDict(extra="forbid")
    action_id: str = Field(min_length=1, max_length=100)
    expected_revision: int = Field(ge=0)
    use_completed_only: bool = False

    def to_command(self):
        from app.agent.graph.update_matching import UpdateBatchRequest
        return UpdateBatchRequest(**self.model_dump(by_alias=False))


class CareerAgentRunStateResponse(CamelCaseModel):
    thread_id: str
    run_id: str
    status: CareerAgentStatus
    current_step: str
    revision: int = 0
    legacy_read_only: bool = False
    requested_job_ids: list[str]
    ranked_job_ids: list[str]
    proposed_target_job_ids: list[str]
    target_suggestion_mode: Literal["supported", "challenge_only"] | None = None
    confirmed_target_job_ids: list[str]
    pending_approval: bool
    interrupt_id: str | None
    human_decision: str | None
    decision_action_id: str | None = None
    gap_result_fingerprint: str | None
    result_id: str | None = None
    update_source_thread_id: str | None = None
    update_source_result_id: str | None = None
    update_scope: Literal["targets", "batch"] | None = None
    update_partial: bool = False
    update_steps: list[UpdateMatchStepResponse] = Field(default_factory=list)

    @classmethod
    def from_state(cls, state: CareerAgentState) -> "CareerAgentRunStateResponse":
        return cls(
            thread_id=state.thread_id,
            run_id=state.run_id,
            status=state.status,
            current_step=state.current_step,
            revision=state.revision,
            legacy_read_only=state.legacy_read_only,
            requested_job_ids=list(state.requested_job_ids),
            ranked_job_ids=list(state.ranked_job_ids),
            proposed_target_job_ids=list(state.proposed_target_job_ids),
            target_suggestion_mode=state.target_suggestion_mode,
            confirmed_target_job_ids=list(state.confirmed_target_job_ids),
            pending_approval=state.pending_approval,
            interrupt_id=state.interrupt_id,
            human_decision=state.human_decision,
            decision_action_id=state.decision_action_id,
            gap_result_fingerprint=state.gap_result_fingerprint,
            result_id=state.result_id,
            update_source_thread_id=state.update_source_thread_id,
            update_source_result_id=state.update_source_result_id,
            update_scope=state.update_scope,
            update_partial=state.update_partial,
            update_steps=[UpdateMatchStepResponse(job_id=s.job_id, extraction_id=s.extraction_id,
                status=s.status, report_id=s.report_id, attempt=s.attempt, error_code=s.error_code) for s in state.update_steps],
        )


class CareerAgentResumeRequest(CamelCaseModel):
    interrupt_id: str = Field(min_length=1)
    action_id: str = Field(min_length=1)
    decision: Literal["approve", "edit", "reject"]
    selected_job_ids: list[str] = Field(default_factory=list, max_length=5)

    def to_command(self, *, thread_id: str) -> ResumeCareerAgentRunRequest:
        return ResumeCareerAgentRunRequest(
            thread_id=thread_id,
            interrupt_id=self.interrupt_id,
            action_id=self.action_id,
            decision=self.decision,
            selected_job_ids=tuple(self.selected_job_ids),
        )


class CareerAgentRunListResponse(CamelCaseModel):
    items: list[CareerAgentRunStateResponse]

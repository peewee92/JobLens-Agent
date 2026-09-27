"""HTTP contracts for Application Workspace."""
from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.api.v1.schemas.common import CamelCaseModel
from app.application.application_workspace.models import (
    ApplicationTimelineEvent,
    ApplicationWorkspace,
    ApplicationWorkspaceStatus,
)
from app.application.application_workspace.status_use_case import UpdateApplicationStatusCommand
from app.application.application_workspace.interview_mock import (
    InterviewAnswerReview,
    InterviewMockQuestionSet,
)
from app.application.application_workspace.resume_variant import ResumeVariant, ResumeVariantProposal, ResumeVariantStatus
from app.application.application_workspace.execution_action import ExecutionActionItem, ExecutionActionStatus
from app.application.application_workspace.evidence_proposal import EvidenceProposal
from app.application.application_workspace.rematch import ApplicationRematchResult
from app.domain.career_context import EvidenceType, SkillLevel
from app.application.application_workspace.use_case import CreateApplicationWorkspaceCommand


class CreateApplicationWorkspaceRequest(CamelCaseModel):
    job_id: str = Field(min_length=1, max_length=100)
    actor_id: str = Field(min_length=1, max_length=100)
    idempotency_key: str = Field(min_length=1, max_length=160)

    def to_command(self) -> CreateApplicationWorkspaceCommand:
        return CreateApplicationWorkspaceCommand(
            job_id=self.job_id,
            actor_id=self.actor_id,
            idempotency_key=self.idempotency_key,
        )


class UpdateApplicationStatusRequest(CamelCaseModel):
    actor_id: str = Field(min_length=1, max_length=100)
    idempotency_key: str = Field(min_length=1, max_length=160)
    expected_status: ApplicationWorkspaceStatus
    new_status: ApplicationWorkspaceStatus

    def to_command(self, workspace_id: str) -> UpdateApplicationStatusCommand:
        return UpdateApplicationStatusCommand(
            workspace_id=workspace_id,
            actor_id=self.actor_id,
            idempotency_key=self.idempotency_key,
            expected_status=self.expected_status,
            new_status=self.new_status,
        )


class SaveResumeVariantRequest(CamelCaseModel):
    actor_id: str = Field(min_length=1, max_length=100)
    idempotency_key: str = Field(min_length=1, max_length=160)


class ReviewResumeVariantRequest(CamelCaseModel):
    actor_id: str = Field(min_length=1, max_length=100)
    expected_status: ResumeVariantStatus = ResumeVariantStatus.DRAFT


class ResumeVariantItemResponse(CamelCaseModel):
    requirement_id: str
    capability: str
    evidence_ids: list[str]


class ResumeVariantProposalResponse(CamelCaseModel):
    workspace_id: str
    job_id: str
    source_profile_id: str
    source_profile_version: int
    requirement_extraction_id: str
    highlights: list[ResumeVariantItemResponse]
    unresolved_requirement_ids: list[str]

    @classmethod
    def from_model(cls, proposal: ResumeVariantProposal) -> "ResumeVariantProposalResponse":
        return cls(
            workspace_id=proposal.workspace_id, job_id=proposal.job_id,
            source_profile_id=proposal.source_profile_id, source_profile_version=proposal.source_profile_version,
            requirement_extraction_id=proposal.requirement_extraction_id,
            highlights=[ResumeVariantItemResponse(requirement_id=item.requirement_id, capability=item.capability, evidence_ids=list(item.evidence_ids)) for item in proposal.highlights],
            unresolved_requirement_ids=list(proposal.unresolved_requirement_ids),
        )


class ResumeVariantResponse(CamelCaseModel):
    variant_id: str
    workspace_id: str
    status: str
    source_profile_id: str
    source_profile_version: int
    requirement_extraction_id: str
    highlights: list[ResumeVariantItemResponse]
    created_at: datetime

    @classmethod
    def from_model(cls, variant: ResumeVariant) -> "ResumeVariantResponse":
        return cls(
            variant_id=variant.variant_id, workspace_id=variant.workspace_id, status=variant.status.value,
            source_profile_id=variant.source_profile_id, source_profile_version=variant.source_profile_version,
            requirement_extraction_id=variant.requirement_extraction_id,
            highlights=[ResumeVariantItemResponse(requirement_id=item.requirement_id, capability=item.capability, evidence_ids=list(item.evidence_ids)) for item in variant.highlights],
            created_at=variant.created_at,
        )


class CreateExecutionActionsRequest(CamelCaseModel):
    actor_id: str = Field(min_length=1, max_length=100)
    idempotency_key: str = Field(min_length=1, max_length=160)


class UpdateExecutionActionStatusRequest(CamelCaseModel):
    actor_id: str = Field(min_length=1, max_length=100)
    expected_status: ExecutionActionStatus
    new_status: ExecutionActionStatus


class ExecutionActionResponse(CamelCaseModel):
    action_id: str
    workspace_id: str
    action_type: str
    status: str
    source_requirement_ids: list[str]
    source_gap_capability: str | None
    description: str
    completion_criteria: list[str]
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None

    @classmethod
    def from_model(cls, action: ExecutionActionItem) -> "ExecutionActionResponse":
        return cls(
            action_id=action.action_id, workspace_id=action.workspace_id,
            action_type=action.action_type.value, status=action.status.value,
            source_requirement_ids=list(action.source_requirement_ids),
            source_gap_capability=action.source_gap_capability, description=action.description,
            completion_criteria=list(action.completion_criteria), created_at=action.created_at,
            updated_at=action.updated_at, completed_at=action.completed_at,
        )


class CreateEvidenceProposalRequest(CamelCaseModel):
    actor_id: str = Field(min_length=1, max_length=100)
    idempotency_key: str = Field(min_length=1, max_length=160)
    evidence_type: EvidenceType
    evidence_summary: str = Field(min_length=1, max_length=2000)
    evidence_source: str = Field(min_length=1, max_length=1000)
    skill_level: SkillLevel


class ConfirmEvidenceProposalRequest(CamelCaseModel):
    actor_id: str = Field(min_length=1, max_length=100)


class EvidenceProposalResponse(CamelCaseModel):
    proposal_id: str
    workspace_id: str
    action_id: str
    status: str
    source_requirement_ids: list[str]
    capability: str
    evidence_type: str
    evidence_summary: str
    evidence_source: str
    skill_level: str
    source_profile_id: str
    source_profile_version: int
    created_at: datetime
    confirmed_profile_id: str | None = None
    confirmed_profile_version: int | None = None
    confirmed_at: datetime | None = None

    @classmethod
    def from_model(cls, proposal: EvidenceProposal) -> "EvidenceProposalResponse":
        return cls(
            proposal_id=proposal.proposal_id, workspace_id=proposal.workspace_id, action_id=proposal.action_id,
            status=proposal.status.value, source_requirement_ids=list(proposal.source_requirement_ids),
            capability=proposal.capability, evidence_type=proposal.evidence_type.value,
            evidence_summary=proposal.evidence_summary, evidence_source=proposal.evidence_source,
            skill_level=proposal.skill_level.value, source_profile_id=proposal.source_profile_id,
            source_profile_version=proposal.source_profile_version, created_at=proposal.created_at,
            confirmed_profile_id=proposal.confirmed_profile_id,
            confirmed_profile_version=proposal.confirmed_profile_version,
            confirmed_at=proposal.confirmed_at,
        )


class ReviewInterviewMockAnswerRequest(CamelCaseModel):
    answer_text: str = Field(min_length=1, max_length=12000)
    evidence_ids: list[str] = Field(default_factory=list, max_length=50)
    actor_id: str = Field(min_length=1, max_length=200)
    idempotency_key: str = Field(min_length=1, max_length=200)


class InterviewMockQuestionResponse(CamelCaseModel):
    question_id: str
    requirement_id: str
    requirement_text: str
    preparation_priority: str
    evidence_status: str
    allowed_evidence_ids: list[str]
    prompt: str


class InterviewMockQuestionSetResponse(CamelCaseModel):
    workspace_id: str
    job_id: str
    source_profile_id: str
    source_profile_version: int
    requirement_extraction_id: str
    questions: list[InterviewMockQuestionResponse]

    @classmethod
    def from_model(cls, question_set: InterviewMockQuestionSet) -> "InterviewMockQuestionSetResponse":
        return cls(
            workspace_id=question_set.workspace_id,
            job_id=question_set.job_id,
            source_profile_id=question_set.source_profile_id,
            source_profile_version=question_set.source_profile_version,
            requirement_extraction_id=question_set.requirement_extraction_id,
            questions=[
                InterviewMockQuestionResponse(
                    question_id=item.question_id,
                    requirement_id=item.requirement_id,
                    requirement_text=item.requirement_text,
                    preparation_priority=item.preparation_priority,
                    evidence_status=item.evidence_status,
                    allowed_evidence_ids=list(item.allowed_evidence_ids),
                    prompt=item.prompt,
                )
                for item in question_set.questions
            ],
        )


class InterviewAnswerReviewResponse(CamelCaseModel):
    workspace_id: str
    question_id: str
    requirement_id: str
    grounding_status: str
    accepted_evidence_ids: list[str]
    rejected_evidence_ids: list[str]
    feedback: list[str]
    retry_recommended: bool
    provider_calls: int
    db_writes: int

    @classmethod
    def from_model(cls, review: InterviewAnswerReview) -> "InterviewAnswerReviewResponse":
        return cls(
            workspace_id=review.workspace_id,
            question_id=review.question_id,
            requirement_id=review.requirement_id,
            grounding_status=review.grounding_status.value,
            accepted_evidence_ids=list(review.accepted_evidence_ids),
            rejected_evidence_ids=list(review.rejected_evidence_ids),
            feedback=list(review.feedback),
            retry_recommended=review.retry_recommended,
            provider_calls=review.provider_calls,
            db_writes=review.db_writes,
        )


class ApplicationRematchRequest(CamelCaseModel):
    actor_id: str = Field(min_length=1, max_length=100)
    idempotency_key: str = Field(min_length=1, max_length=160)


class ApplicationRematchResponse(CamelCaseModel):
    workspace_id: str
    proposal_id: str
    previous_match_report_id: str
    current_match_report_id: str
    previous_recommendation: str
    current_recommendation: str
    resolved_requirement_ids: list[str]
    target_requirement_ids: list[str]
    target_resolved_requirement_ids: list[str]
    ranking_signal: str
    provider_calls: int

    @classmethod
    def from_model(cls, result: ApplicationRematchResult) -> "ApplicationRematchResponse":
        return cls(
            workspace_id=result.workspace_id,
            proposal_id=result.proposal_id,
            previous_match_report_id=result.previous_match_report_id,
            current_match_report_id=result.current_match_report_id,
            previous_recommendation=result.previous_recommendation.value,
            current_recommendation=result.current_recommendation.value,
            resolved_requirement_ids=list(result.resolved_requirement_ids),
            target_requirement_ids=list(result.target_requirement_ids),
            target_resolved_requirement_ids=list(result.target_resolved_requirement_ids),
            ranking_signal=result.ranking_signal.value,
            provider_calls=result.provider_calls,
        )


class ApplicationTimelineEventResponse(CamelCaseModel):
    event_id: str
    workspace_id: str
    actor_id: str
    event_type: str
    from_status: str | None
    to_status: str | None
    created_at: datetime

    @classmethod
    def from_model(cls, event: ApplicationTimelineEvent) -> "ApplicationTimelineEventResponse":
        return cls(
            event_id=event.event_id,
            workspace_id=event.workspace_id,
            actor_id=event.actor_id,
            event_type=event.event_type.value,
            from_status=event.from_status.value if event.from_status is not None else None,
            to_status=event.to_status.value if event.to_status is not None else None,
            created_at=event.created_at,
        )


class ApplicationWorkspaceSourceSnapshotResponse(CamelCaseModel):
    profile_id: str
    profile_version: int
    search_intent_id: str
    search_intent_version: int
    requirement_extraction_id: str
    match_report_id: str


class ApplicationNextBestActionResponse(CamelCaseModel):
    code: str
    label: str
    reason: str
    href: str


class ApplicationWorkspaceOverviewResponse(CamelCaseModel):
    workspace: "ApplicationWorkspaceResponse"
    resume_status: str
    action_total: int
    action_open: int
    evidence_pending_confirmation: int
    evidence_confirmed: int
    timeline_event_count: int
    next_best_action: ApplicationNextBestActionResponse

    @classmethod
    def from_model(cls, overview):
        return cls(
            workspace=ApplicationWorkspaceResponse.from_model(overview.workspace),
            resume_status=overview.resume_status,
            action_total=overview.action_total,
            action_open=overview.action_open,
            evidence_pending_confirmation=overview.evidence_pending_confirmation,
            evidence_confirmed=overview.evidence_confirmed,
            timeline_event_count=overview.timeline_event_count,
            next_best_action=ApplicationNextBestActionResponse(
                code=overview.next_best_action.code,
                label=overview.next_best_action.label,
                reason=overview.next_best_action.reason,
                href=overview.next_best_action.href,
            ),
        )


class ApplicationWorkspaceResponse(CamelCaseModel):
    workspace_id: str
    job_id: str
    actor_id: str
    status: str
    source_snapshot: ApplicationWorkspaceSourceSnapshotResponse
    current_fact_fingerprint: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, workspace: ApplicationWorkspace) -> "ApplicationWorkspaceResponse":
        return cls(
            workspace_id=workspace.workspace_id,
            job_id=workspace.job_id,
            actor_id=workspace.actor_id,
            status=workspace.status.value,
            source_snapshot=ApplicationWorkspaceSourceSnapshotResponse(
                profile_id=workspace.source_snapshot.profile_id,
                profile_version=workspace.source_snapshot.profile_version,
                search_intent_id=workspace.source_snapshot.search_intent_id,
                search_intent_version=workspace.source_snapshot.search_intent_version,
                requirement_extraction_id=workspace.source_snapshot.requirement_extraction_id,
                match_report_id=workspace.source_snapshot.match_report_id,
            ),
            current_fact_fingerprint=workspace.current_fact_fingerprint,
            created_at=workspace.created_at,
            updated_at=workspace.updated_at,
        )

"""vNext 1.2 Application Workspace endpoints."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import (
    get_application_timeline_repository,
    get_application_workspace_overview_use_case,
    get_application_workspace_repository,
    get_create_application_workspace_use_case,
    get_create_study_execution_actions_use_case,
    get_execution_action_repository,
    get_create_evidence_proposal_use_case,
    get_confirm_evidence_proposal_use_case,
    get_interview_mock_question_set_use_case,
    get_application_rematch_use_case,
    get_review_interview_mock_answer_use_case,
    get_resume_variant_proposal_use_case,
    get_review_resume_variant_use_case,
    get_save_resume_variant_use_case,
    get_update_application_status_use_case,
    get_update_execution_action_status_use_case,
)
from app.api.v1.schemas.application_workspace import (
    ApplicationRematchRequest,
    ApplicationRematchResponse,
    ApplicationTimelineEventResponse,
    ApplicationWorkspaceOverviewResponse,
    ApplicationWorkspaceResponse,
    CreateApplicationWorkspaceRequest,
    CreateExecutionActionsRequest,
    ExecutionActionResponse,
    CreateEvidenceProposalRequest,
    ConfirmEvidenceProposalRequest,
    EvidenceProposalResponse,
    InterviewAnswerReviewResponse,
    InterviewMockQuestionSetResponse,
    ReviewInterviewMockAnswerRequest,
    UpdateApplicationStatusRequest,
    UpdateExecutionActionStatusRequest,
    ResumeVariantProposalResponse,
    ResumeVariantResponse,
    ReviewResumeVariantRequest,
    SaveResumeVariantRequest,
)
from app.application.application_workspace.evidence_proposal import ConfirmEvidenceProposalUseCase, CreateEvidenceProposalUseCase, EvidenceProposalBlockedError
from app.application.application_workspace.rematch import ApplicationRematchBlockedError, RunApplicationRematchUseCase
from app.application.application_workspace.execution_action import (
    CreateStudyExecutionActionsUseCase,
    ExecutionActionBlockedError,
    UpdateExecutionActionStatusUseCase,
)
from app.application.application_workspace.interview_mock import (
    BuildInterviewMockQuestionSetUseCase,
    InterviewMockBlockedError,
    ReviewInterviewMockAnswerUseCase,
)
from app.application.application_workspace.resume_variant import (
    BuildResumeVariantProposalUseCase,
    ResumeVariantBlockedError,
    ReviewResumeVariantUseCase,
    SaveResumeVariantUseCase,
)
from app.application.application_workspace.status_use_case import (
    ApplicationStatusBlockedError,
    UpdateApplicationStatusUseCase,
)
from app.application.application_workspace.use_case import (
    ApplicationWorkspaceBlockedError,
    CreateApplicationWorkspaceUseCase,
)
from app.repositories.sqlalchemy_application_workspace_repository import (
    SqlAlchemyApplicationTimelineRepository,
    SqlAlchemyApplicationWorkspaceRepository,
    SqlAlchemyExecutionActionRepository,
)

router = APIRouter(prefix="/application-workspaces")


@router.post("", response_model=ApplicationWorkspaceResponse, status_code=status.HTTP_201_CREATED)
def create_application_workspace(
    request: CreateApplicationWorkspaceRequest,
    use_case: Annotated[
        CreateApplicationWorkspaceUseCase,
        Depends(get_create_application_workspace_use_case),
    ],
) -> ApplicationWorkspaceResponse:
    try:
        workspace = use_case.execute(request.to_command())
    except ApplicationWorkspaceBlockedError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    return ApplicationWorkspaceResponse.from_model(workspace)


@router.post("/{workspace_id}/status", response_model=ApplicationWorkspaceResponse)
def update_application_status(
    workspace_id: str,
    request: UpdateApplicationStatusRequest,
    use_case: Annotated[
        UpdateApplicationStatusUseCase,
        Depends(get_update_application_status_use_case),
    ],
) -> ApplicationWorkspaceResponse:
    try:
        result = use_case.execute(request.to_command(workspace_id))
    except ApplicationStatusBlockedError as error:
        detail = str(error)
        status_code = (
            status.HTTP_404_NOT_FOUND
            if detail == "application_workspace_not_found"
            else status.HTTP_409_CONFLICT
        )
        raise HTTPException(status_code=status_code, detail=detail) from error
    return ApplicationWorkspaceResponse.from_model(result.workspace)


@router.get("/{workspace_id}/overview", response_model=ApplicationWorkspaceOverviewResponse)
def get_application_workspace_overview(
    workspace_id: str,
    use_case=Depends(get_application_workspace_overview_use_case),
) -> ApplicationWorkspaceOverviewResponse:
    from app.application.application_workspace.overview import ApplicationWorkspaceOverviewBlockedError
    try:
        return ApplicationWorkspaceOverviewResponse.from_model(use_case.execute(workspace_id))
    except ApplicationWorkspaceOverviewBlockedError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


@router.get("/{workspace_id}/interview/questions", response_model=InterviewMockQuestionSetResponse)
def get_interview_mock_questions(
    workspace_id: str,
    use_case: Annotated[
        BuildInterviewMockQuestionSetUseCase,
        Depends(get_interview_mock_question_set_use_case),
    ],
) -> InterviewMockQuestionSetResponse:
    try:
        return InterviewMockQuestionSetResponse.from_model(use_case.execute(workspace_id))
    except InterviewMockBlockedError as error:
        detail = str(error)
        code = status.HTTP_404_NOT_FOUND if detail == "application_workspace_not_found" else status.HTTP_409_CONFLICT
        raise HTTPException(status_code=code, detail=detail) from error


@router.post(
    "/{workspace_id}/interview/questions/{question_id}/review",
    response_model=InterviewAnswerReviewResponse,
)
def review_interview_mock_answer(
    workspace_id: str,
    question_id: str,
    request: ReviewInterviewMockAnswerRequest,
    use_case: Annotated[
        ReviewInterviewMockAnswerUseCase,
        Depends(get_review_interview_mock_answer_use_case),
    ],
) -> InterviewAnswerReviewResponse:
    try:
        review = use_case.execute(
            workspace_id=workspace_id,
            question_id=question_id,
            answer_text=request.answer_text,
            evidence_ids=tuple(request.evidence_ids),
        )
    except InterviewMockBlockedError as error:
        detail = str(error)
        code = status.HTTP_404_NOT_FOUND if detail in {"application_workspace_not_found", "interview_question_not_found"} else status.HTTP_409_CONFLICT
        raise HTTPException(status_code=code, detail=detail) from error
    return InterviewAnswerReviewResponse.from_model(review)


@router.get("/{workspace_id}/resume-variant/proposal", response_model=ResumeVariantProposalResponse)
def get_resume_variant_proposal(
    workspace_id: str,
    use_case: Annotated[BuildResumeVariantProposalUseCase, Depends(get_resume_variant_proposal_use_case)],
) -> ResumeVariantProposalResponse:
    try:
        return ResumeVariantProposalResponse.from_model(use_case.execute(workspace_id))
    except ResumeVariantBlockedError as error:
        detail = str(error)
        code = status.HTTP_404_NOT_FOUND if detail == "application_workspace_not_found" else status.HTTP_409_CONFLICT
        raise HTTPException(status_code=code, detail=detail) from error


@router.post("/{workspace_id}/resume-variants", response_model=ResumeVariantResponse, status_code=status.HTTP_201_CREATED)
def save_resume_variant(
    workspace_id: str,
    request: SaveResumeVariantRequest,
    use_case: Annotated[SaveResumeVariantUseCase, Depends(get_save_resume_variant_use_case)],
) -> ResumeVariantResponse:
    try:
        variant = use_case.execute(workspace_id=workspace_id, actor_id=request.actor_id, idempotency_key=request.idempotency_key)
    except ResumeVariantBlockedError as error:
        detail = str(error)
        code = status.HTTP_404_NOT_FOUND if detail == "application_workspace_not_found" else status.HTTP_409_CONFLICT
        raise HTTPException(status_code=code, detail=detail) from error
    return ResumeVariantResponse.from_model(variant)


@router.post("/{workspace_id}/resume-variants/{variant_id}/review", response_model=ResumeVariantResponse)
def review_resume_variant(
    workspace_id: str,
    variant_id: str,
    request: ReviewResumeVariantRequest,
    use_case: Annotated[ReviewResumeVariantUseCase, Depends(get_review_resume_variant_use_case)],
) -> ResumeVariantResponse:
    try:
        variant = use_case.execute(
            workspace_id=workspace_id,
            variant_id=variant_id,
            actor_id=request.actor_id,
            expected_status=request.expected_status,
        )
    except ResumeVariantBlockedError as error:
        detail = str(error)
        code = status.HTTP_404_NOT_FOUND if detail == "resume_variant_not_found" else status.HTTP_409_CONFLICT
        raise HTTPException(status_code=code, detail=detail) from error
    return ResumeVariantResponse.from_model(variant)


@router.post("/{workspace_id}/actions", response_model=list[ExecutionActionResponse], status_code=status.HTTP_201_CREATED)
def create_execution_actions(
    workspace_id: str,
    request: CreateExecutionActionsRequest,
    use_case: Annotated[CreateStudyExecutionActionsUseCase, Depends(get_create_study_execution_actions_use_case)],
) -> list[ExecutionActionResponse]:
    try:
        actions = use_case.execute(workspace_id=workspace_id, actor_id=request.actor_id, idempotency_key=request.idempotency_key)
    except ExecutionActionBlockedError as error:
        detail = str(error)
        code = status.HTTP_404_NOT_FOUND if detail == "application_workspace_not_found" else status.HTTP_409_CONFLICT
        raise HTTPException(status_code=code, detail=detail) from error
    return [ExecutionActionResponse.from_model(action) for action in actions]


@router.get("/{workspace_id}/actions", response_model=list[ExecutionActionResponse])
def list_execution_actions(
    workspace_id: str,
    workspaces: Annotated[SqlAlchemyApplicationWorkspaceRepository, Depends(get_application_workspace_repository)],
    actions: Annotated[SqlAlchemyExecutionActionRepository, Depends(get_execution_action_repository)],
) -> list[ExecutionActionResponse]:
    if workspaces.get(workspace_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="application_workspace_not_found")
    return [ExecutionActionResponse.from_model(action) for action in actions.list_for_workspace(workspace_id)]


@router.post("/{workspace_id}/actions/{action_id}/status", response_model=ExecutionActionResponse)
def update_execution_action_status(
    workspace_id: str,
    action_id: str,
    request: UpdateExecutionActionStatusRequest,
    use_case: Annotated[UpdateExecutionActionStatusUseCase, Depends(get_update_execution_action_status_use_case)],
) -> ExecutionActionResponse:
    try:
        action = use_case.execute(workspace_id=workspace_id, action_id=action_id, actor_id=request.actor_id, expected_status=request.expected_status, new_status=request.new_status)
    except ExecutionActionBlockedError as error:
        detail = str(error)
        code = status.HTTP_404_NOT_FOUND if detail == "execution_action_not_found" else status.HTTP_409_CONFLICT
        raise HTTPException(status_code=code, detail=detail) from error
    return ExecutionActionResponse.from_model(action)


@router.post("/{workspace_id}/actions/{action_id}/evidence-proposals", response_model=EvidenceProposalResponse, status_code=status.HTTP_201_CREATED)
def create_evidence_proposal(
    workspace_id: str,
    action_id: str,
    request: CreateEvidenceProposalRequest,
    use_case: Annotated[CreateEvidenceProposalUseCase, Depends(get_create_evidence_proposal_use_case)],
) -> EvidenceProposalResponse:
    try:
        proposal = use_case.execute(
            workspace_id=workspace_id, action_id=action_id, actor_id=request.actor_id,
            idempotency_key=request.idempotency_key, evidence_type=request.evidence_type,
            evidence_summary=request.evidence_summary, evidence_source=request.evidence_source,
            skill_level=request.skill_level,
        )
    except EvidenceProposalBlockedError as error:
        detail = str(error)
        code = status.HTTP_404_NOT_FOUND if detail == "execution_action_not_found" else status.HTTP_409_CONFLICT
        raise HTTPException(status_code=code, detail=detail) from error
    return EvidenceProposalResponse.from_model(proposal)


@router.post("/{workspace_id}/evidence-proposals/{proposal_id}/confirm", response_model=EvidenceProposalResponse)
def confirm_evidence_proposal(
    workspace_id: str,
    proposal_id: str,
    request: ConfirmEvidenceProposalRequest,
    use_case: Annotated[ConfirmEvidenceProposalUseCase, Depends(get_confirm_evidence_proposal_use_case)],
) -> EvidenceProposalResponse:
    try:
        proposal = use_case.execute(
            workspace_id=workspace_id,
            proposal_id=proposal_id,
            actor_id=request.actor_id,
        )
    except EvidenceProposalBlockedError as error:
        detail = str(error)
        code = status.HTTP_404_NOT_FOUND if detail == "evidence_proposal_not_found" else status.HTTP_409_CONFLICT
        raise HTTPException(status_code=code, detail=detail) from error
    return EvidenceProposalResponse.from_model(proposal)


@router.post("/{workspace_id}/evidence-proposals/{proposal_id}/rematch", response_model=ApplicationRematchResponse)
def run_application_rematch(
    workspace_id: str,
    proposal_id: str,
    request: ApplicationRematchRequest,
    use_case: Annotated[RunApplicationRematchUseCase, Depends(get_application_rematch_use_case)],
) -> ApplicationRematchResponse:
    try:
        result = use_case.execute(
            workspace_id=workspace_id,
            proposal_id=proposal_id,
            actor_id=request.actor_id,
            idempotency_key=request.idempotency_key,
        )
    except ApplicationRematchBlockedError as error:
        detail = str(error)
        code = status.HTTP_404_NOT_FOUND if detail == "evidence_proposal_not_found" else status.HTTP_409_CONFLICT
        raise HTTPException(status_code=code, detail=detail) from error
    return ApplicationRematchResponse.from_model(result)


@router.get("/{workspace_id}/timeline", response_model=list[ApplicationTimelineEventResponse])
def list_application_timeline(
    workspace_id: str,
    workspaces: Annotated[
        SqlAlchemyApplicationWorkspaceRepository,
        Depends(get_application_workspace_repository),
    ],
    timeline: Annotated[
        SqlAlchemyApplicationTimelineRepository,
        Depends(get_application_timeline_repository),
    ],
) -> list[ApplicationTimelineEventResponse]:
    if workspaces.get(workspace_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="application_workspace_not_found")
    return [ApplicationTimelineEventResponse.from_model(event) for event in timeline.list_for_workspace(workspace_id)]


@router.get("/{workspace_id}", response_model=ApplicationWorkspaceResponse)
def get_application_workspace(
    workspace_id: str,
    repository: Annotated[
        SqlAlchemyApplicationWorkspaceRepository,
        Depends(get_application_workspace_repository),
    ],
) -> ApplicationWorkspaceResponse:
    workspace = repository.get(workspace_id)
    if workspace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="application_workspace_not_found")
    return ApplicationWorkspaceResponse.from_model(workspace)

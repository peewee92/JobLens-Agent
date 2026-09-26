"""vNext 1.2 Application Workspace endpoints."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import (
    get_application_timeline_repository,
    get_application_workspace_repository,
    get_create_application_workspace_use_case,
    get_update_application_status_use_case,
)
from app.api.v1.schemas.application_workspace import (
    ApplicationTimelineEventResponse,
    ApplicationWorkspaceResponse,
    CreateApplicationWorkspaceRequest,
    UpdateApplicationStatusRequest,
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

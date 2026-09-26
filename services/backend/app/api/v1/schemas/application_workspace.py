"""HTTP contracts for Application Workspace."""
from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.api.v1.schemas.common import CamelCaseModel
from app.application.application_workspace.models import ApplicationWorkspace
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


class ApplicationWorkspaceSourceSnapshotResponse(CamelCaseModel):
    profile_id: str
    profile_version: int
    search_intent_id: str
    search_intent_version: int
    requirement_extraction_id: str
    match_report_id: str


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

from dataclasses import asdict
from datetime import datetime
from pydantic import Field
from app.api.v1.schemas.common import CamelCaseModel


class WorkbenchActionResponse(CamelCaseModel):
    code: str
    label: str
    reason: str
    href: str


class WorkbenchRunResponse(CamelCaseModel):
    thread_id: str
    status: str
    current_step: str
    job_count: int
    target_count: int
    execution_target_count: int
    result_id: str | None
    result_is_current: bool | None
    updated_at: datetime
    partial: bool = False
    completed_report_count: int = 0


class WorkbenchWorkspaceResponse(CamelCaseModel):
    workspace_id: str
    job_id: str
    title: str
    status: str
    open_action_count: int
    current_analysis_thread_id: str | None


class WorkbenchChangeResponse(CamelCaseModel):
    kind: str
    occurred_at: datetime
    href: str


class WorkbenchSnapshotResponse(CamelCaseModel):
    profile_version: int | None
    search_intent_version: int | None
    evidence_count: int
    input_issue_codes: list[str]
    job_count: int
    current_run: WorkbenchRunResponse | None
    workspaces: list[WorkbenchWorkspaceResponse] = Field(max_length=5)
    changes: list[WorkbenchChangeResponse] = Field(max_length=10)


class WorkbenchResponse(CamelCaseModel):
    snapshot: WorkbenchSnapshotResponse
    next_action: WorkbenchActionResponse

    @classmethod
    def from_result(cls, result):
        return cls.model_validate(asdict(result))

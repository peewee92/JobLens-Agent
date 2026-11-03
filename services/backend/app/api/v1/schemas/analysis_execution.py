"""Commands and receipts for a saved analysis becoming a workspace."""
from dataclasses import asdict
from pydantic import Field
from app.api.v1.schemas.common import CamelCaseModel
from app.api.v1.schemas.job_preparation import JobPreparationResponse
from app.application.application_workspace.start_analysis_execution import StartAnalysisExecutionCommand


class StartAnalysisExecutionRequest(CamelCaseModel):
    command_id: str = Field(min_length=1, max_length=120)
    result_id: str = Field(min_length=1, max_length=120)
    job_ids: list[str] = Field(min_length=1, max_length=5)

    def to_command(self, thread_id):
        return StartAnalysisExecutionCommand(thread_id, self.command_id, self.result_id, tuple(dict.fromkeys(self.job_ids)))


class AnalysisExecutionWorkspaceResponse(CamelCaseModel):
    job_id: str
    workspace_id: str
    resume_variant_id: str | None
    action_ids: list[str]


class AnalysisExecutionResponse(CamelCaseModel):
    thread_id: str
    result_id: str
    command_id: str
    items: list[AnalysisExecutionWorkspaceResponse]

    @classmethod
    def from_result(cls, result):
        return cls(thread_id=result.thread_id, result_id=result.result_id, command_id=result.command_id,
            items=[AnalysisExecutionWorkspaceResponse(**asdict(item)) for item in result.items])


class AnalysisExecutionStatusResponse(CamelCaseModel):
    execution: AnalysisExecutionResponse | None


class WorkspaceSavedPreparationResponse(CamelCaseModel):
    thread_id: str
    result_id: str
    is_current: bool
    stale_reasons: list[str]
    preparation: JobPreparationResponse

    @classmethod
    def from_result(cls, result):
        return cls(thread_id=result.thread_id, result_id=result.result_id, is_current=result.is_current,
            stale_reasons=list(result.stale_reasons), preparation=JobPreparationResponse.from_result(result.bundle))

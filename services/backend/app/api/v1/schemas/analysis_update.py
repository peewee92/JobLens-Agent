from dataclasses import asdict
from pydantic import Field, ConfigDict
from typing import Literal
from app.api.v1.schemas.common import CamelCaseModel
from app.application.analysis_update import AnalysisUpdatePlan


class AnalysisUpdateItemResponse(CamelCaseModel):
    job_id: str
    title: str
    status: Literal['reuse', 'ready', 'deferred', 'requires_model', 'input_blocked']
    extraction_id: str | None
    reusable_report_id: str | None
    stale_reasons: list[str]
    blocker_codes: list[str]
    required_operations: list[str]
    input_fingerprint: str
    base_report_id: str | None
    repair_href: str


class AnalysisUpdatePlanResponse(CamelCaseModel):
    source_thread_id: str
    source_result_id: str
    scope: Literal['targets', 'batch']
    previous_profile_version: int
    profile_id: str | None
    profile_version: int | None
    search_intent_id: str | None
    search_intent_version: int | None
    max_new_analyses: Literal[5]
    items: list[AnalysisUpdateItemResponse]
    next_job_ids: list[str]
    reusable_job_ids: list[str]
    input_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    advisory_only: Literal[True]

    @classmethod
    def from_result(cls, result: AnalysisUpdatePlan):
        return cls.model_validate(asdict(result))


class StartAnalysisUpdateRequest(CamelCaseModel):
    model_config = ConfigDict(extra="forbid")
    thread_id: str = Field(min_length=1, max_length=100)
    run_id: str = Field(min_length=1, max_length=100)
    request_id: str = Field(min_length=1, max_length=100)
    source_result_id: str = Field(min_length=1, max_length=100)
    scope: Literal["targets", "batch"]
    input_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    top_n: int = Field(default=3, ge=1, le=5)

    def to_command(self, source_thread_id):
        from app.agent.graph.hitl_service import UpdateCareerAgentRunRequest
        return UpdateCareerAgentRunRequest(source_thread_id=source_thread_id, **self.model_dump(by_alias=False))

"""Explicit one-job authorization, same bounded command as requirement extraction."""
from typing import Literal
from app.api.v1.schemas.common import CamelCaseModel
from app.api.v1.schemas.requirement_calls import RequirementCallCommand


class SemanticCallCommand(RequirementCallCommand):
    pass


class SemanticCallRecord(CamelCaseModel):
    action_id: str
    job_id: str
    status: Literal["running", "completed", "failed", "uncertain"]
    attempts: int
    response_status: int | None
    input_tokens: int | None
    output_tokens: int | None
    report_id: str | None
    error_code: str | None
    model: str
    max_output_tokens: int
    timeout_seconds: float


class CandidatePreview(CamelCaseModel):
    evidence_id: str
    summary: str


class RequirementPreview(CamelCaseModel):
    requirement_id: str
    requirement_text: str
    candidates: list[CandidatePreview]


class SemanticCallPlan(CamelCaseModel):
    execution_mode: Literal["offline", "authorized"]
    job_id: str
    plan_digest: str
    available: bool
    blocker_code: str | None
    model: str
    max_provider_calls: Literal[1]
    max_output_tokens: int
    timeout_seconds: float
    profile_version: int
    search_intent_version: int | None
    extraction_id: str
    requirements: list[RequirementPreview]
    latest_request: SemanticCallRecord | None

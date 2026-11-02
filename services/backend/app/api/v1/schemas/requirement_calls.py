"""Bounded extraction authorization; no monetary price is inferred from tokens."""
from typing import Literal
from pydantic import ConfigDict, Field, StrictBool
from app.api.v1.schemas.common import CamelCaseModel


class RequirementCallCommand(CamelCaseModel):
    model_config = ConfigDict(extra="forbid")
    action_id: str = Field(min_length=1, max_length=100, pattern=r"^\S+$")
    plan_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    confirmed: StrictBool = False
    max_provider_calls: int = Field(default=0, ge=0, le=1, strict=True)
    acknowledged_prior_request_id: str | None = Field(default=None, min_length=1, max_length=100)


class RequirementCallRecord(CamelCaseModel):
    action_id: str
    job_id: str
    status: Literal["running", "completed", "failed", "uncertain"]
    attempts: int
    response_status: int | None
    input_tokens: int | None
    output_tokens: int | None
    extraction_id: str | None
    error_code: str | None
    model: str
    max_output_tokens: int
    timeout_seconds: float


class RequirementCallPlan(CamelCaseModel):
    job_id: str
    plan_digest: str
    input_hash: str
    available: bool
    blocker_code: str | None
    model: str
    max_provider_calls: Literal[1]
    max_output_tokens: int
    timeout_seconds: float
    description_characters: int
    latest_request: RequirementCallRecord | None

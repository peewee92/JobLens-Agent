"""HTTP contracts for read-only Match input preflight."""
from __future__ import annotations

from app.api.v1.schemas.career_context import CareerContextReleaseReadinessResponse
from app.api.v1.schemas.common import CamelCaseModel
from app.api.v1.schemas.job_requirements import JobRequirementReleaseReadinessResponse
from app.application.match_inputs.readiness import MatchInputReadiness


class MatchInputBlockerResponse(CamelCaseModel):
    source: str
    code: str
    message: str


class MatchInputReadinessResponse(CamelCaseModel):
    job_id: str
    inputs_release_eligible: bool
    career_context: CareerContextReleaseReadinessResponse
    job_requirements: JobRequirementReleaseReadinessResponse
    blockers: list[MatchInputBlockerResponse]
    db_writes: int
    provider_calls: int
    trace_runs_created: int

    @classmethod
    def from_detail(cls, detail: MatchInputReadiness) -> "MatchInputReadinessResponse":
        return cls(
            job_id=detail.job_id,
            inputs_release_eligible=detail.inputs_release_eligible,
            career_context=CareerContextReleaseReadinessResponse.from_detail(
                detail.career_context
            ),
            job_requirements=JobRequirementReleaseReadinessResponse.from_detail(
                detail.job_requirements
            ),
            blockers=[
                MatchInputBlockerResponse(
                    source=item.source.value,
                    code=item.code,
                    message=item.message,
                )
                for item in detail.blockers
            ],
            db_writes=detail.db_writes,
            provider_calls=detail.provider_calls,
            trace_runs_created=detail.trace_runs_created,
        )

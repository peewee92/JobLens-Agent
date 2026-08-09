"""HTTP contracts for deterministic Phase 4 Eligibility."""
from __future__ import annotations

from app.api.v1.schemas.common import CamelCaseModel
from app.application.eligibility import JobEligibilityResult


class RequirementEligibilityResponse(CamelCaseModel):
    requirement_id: str
    requirement_index: int
    type: str
    importance: str
    original_text: str
    normalized_capability: str | None
    status: str
    evidence_ids: list[str]
    profile_fact_refs: list[str]
    reason: str


class JobEligibilityResponse(CamelCaseModel):
    job_id: str
    profile_id: str
    profile_version: int
    extraction_id: str
    eligibility: str
    requirements: list[RequirementEligibilityResponse]
    matched_count: int
    conditional_count: int
    missing_count: int
    db_writes: int
    provider_calls: int
    trace_runs_created: int

    @classmethod
    def from_detail(cls, detail: JobEligibilityResult) -> "JobEligibilityResponse":
        return cls(
            job_id=detail.job_id,
            profile_id=detail.profile_id,
            profile_version=detail.profile_version,
            extraction_id=detail.extraction_id,
            eligibility=detail.eligibility.value,
            requirements=[
                RequirementEligibilityResponse(
                    requirement_id=item.requirement_id,
                    requirement_index=item.requirement_index,
                    type=item.type.value,
                    importance=item.importance.value,
                    original_text=item.original_text,
                    normalized_capability=item.normalized_capability,
                    status=item.status.value,
                    evidence_ids=list(item.evidence_ids),
                    profile_fact_refs=list(item.profile_fact_refs),
                    reason=item.reason,
                )
                for item in detail.requirements
            ],
            matched_count=detail.matched_count,
            conditional_count=detail.conditional_count,
            missing_count=detail.missing_count,
            db_writes=detail.db_writes,
            provider_calls=detail.provider_calls,
            trace_runs_created=detail.trace_runs_created,
        )

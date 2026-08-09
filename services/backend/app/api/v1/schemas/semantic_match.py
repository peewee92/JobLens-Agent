"""HTTP contract for transient Phase 4 Semantic Match results."""
from __future__ import annotations

from app.api.v1.schemas.common import CamelCaseModel
from app.application.semantic_match.models import JobSemanticMatchResult


class SemanticRequirementAssessmentResponse(CamelCaseModel):
    requirement_id: str
    requirement_index: int
    type: str
    importance: str
    original_text: str
    normalized_capability: str | None
    eligibility_status: str
    verdict: str
    evidence_ids: list[str]
    profile_fact_refs: list[str]
    reason: str
    source: str


class JobSemanticMatchResponse(CamelCaseModel):
    job_id: str
    profile_id: str
    profile_version: int
    extraction_id: str
    eligibility: str
    assessments: list[SemanticRequirementAssessmentResponse]
    matched_count: int
    partial_count: int
    not_matched_count: int
    matcher_version: str
    prompt_version: str
    model: str | None
    trace_run_id: str | None
    db_writes: int
    provider_calls: int
    trace_runs_created: int

    @classmethod
    def from_detail(cls, detail: JobSemanticMatchResult) -> "JobSemanticMatchResponse":
        return cls(
            job_id=detail.job_id,
            profile_id=detail.profile_id,
            profile_version=detail.profile_version,
            extraction_id=detail.extraction_id,
            eligibility=detail.eligibility.value,
            assessments=[
                SemanticRequirementAssessmentResponse(
                    requirement_id=item.requirement_id,
                    requirement_index=item.requirement_index,
                    type=item.type.value,
                    importance=item.importance.value,
                    original_text=item.original_text,
                    normalized_capability=item.normalized_capability,
                    eligibility_status=item.eligibility_status.value,
                    verdict=item.verdict.value,
                    evidence_ids=list(item.evidence_ids),
                    profile_fact_refs=list(item.profile_fact_refs),
                    reason=item.reason,
                    source=item.source.value,
                )
                for item in detail.assessments
            ],
            matched_count=detail.matched_count,
            partial_count=detail.partial_count,
            not_matched_count=detail.not_matched_count,
            matcher_version=detail.matcher_version,
            prompt_version=detail.prompt_version,
            model=detail.model,
            trace_run_id=detail.trace_run_id,
            db_writes=detail.db_writes,
            provider_calls=detail.provider_calls,
            trace_runs_created=detail.trace_runs_created,
        )

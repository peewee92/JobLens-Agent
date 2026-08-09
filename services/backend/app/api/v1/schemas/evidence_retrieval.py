"""HTTP contracts for deterministic Phase 4 Evidence Retrieval."""
from __future__ import annotations

from app.api.v1.schemas.common import CamelCaseModel
from app.application.evidence_retrieval import JobEvidenceRetrievalResult


class CandidateEvidenceResponse(CamelCaseModel):
    evidence_id: str
    evidence_key: str
    evidence_type: str
    summary: str
    source: str
    relevance_tier: str
    retrieval_basis: str
    matched_terms: list[str]
    reason: str


class RequirementEvidenceCandidatesResponse(CamelCaseModel):
    requirement_id: str
    requirement_index: int
    type: str
    importance: str
    original_text: str
    normalized_capability: str | None
    candidates: list[CandidateEvidenceResponse]


class JobEvidenceRetrievalResponse(CamelCaseModel):
    job_id: str
    profile_id: str
    profile_version: int
    extraction_id: str
    requirements: list[RequirementEvidenceCandidatesResponse]
    candidate_count: int
    db_writes: int
    provider_calls: int
    trace_runs_created: int

    @classmethod
    def from_detail(
        cls,
        detail: JobEvidenceRetrievalResult,
    ) -> "JobEvidenceRetrievalResponse":
        return cls(
            job_id=detail.job_id,
            profile_id=detail.profile_id,
            profile_version=detail.profile_version,
            extraction_id=detail.extraction_id,
            requirements=[
                RequirementEvidenceCandidatesResponse(
                    requirement_id=item.requirement_id,
                    requirement_index=item.requirement_index,
                    type=item.type.value,
                    importance=item.importance.value,
                    original_text=item.original_text,
                    normalized_capability=item.normalized_capability,
                    candidates=[
                        CandidateEvidenceResponse(
                            evidence_id=candidate.evidence_id,
                            evidence_key=candidate.evidence_key,
                            evidence_type=candidate.evidence_type.value,
                            summary=candidate.summary,
                            source=candidate.source,
                            relevance_tier=candidate.relevance_tier.value,
                            retrieval_basis=candidate.retrieval_basis.value,
                            matched_terms=list(candidate.matched_terms),
                            reason=candidate.reason,
                        )
                        for candidate in item.candidates
                    ],
                )
                for item in detail.requirements
            ],
            candidate_count=detail.candidate_count,
            db_writes=detail.db_writes,
            provider_calls=detail.provider_calls,
            trace_runs_created=detail.trace_runs_created,
        )

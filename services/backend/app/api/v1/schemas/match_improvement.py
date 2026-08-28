"""HTTP contract for the read-only Match improvement comparison."""
from __future__ import annotations

from app.api.v1.schemas.common import CamelCaseModel
from app.application.match_improvement import MatchImprovement


class MatchImprovementRequirementResponse(CamelCaseModel):
    requirement_id: str
    original_text: str


class MatchImprovementEvidenceImpactResponse(CamelCaseModel):
    evidence_id: str
    evidence_type: str
    summary: str
    supporting_requirements: list[MatchImprovementRequirementResponse]


class MatchImprovementResponse(CamelCaseModel):
    job_id: str
    current_report_id: str
    previous_report_id: str | None
    previous_recommendation: str | None
    current_recommendation: str
    previous_profile_version: int | None
    current_profile_version: int
    previous_missing_requirement_count: int | None
    current_missing_requirement_count: int
    resolved_requirement_ids: list[str]
    newly_missing_requirement_ids: list[str]
    resolved_requirements: list[MatchImprovementRequirementResponse]
    newly_missing_requirements: list[MatchImprovementRequirementResponse]
    newly_supporting_evidence: list[MatchImprovementEvidenceImpactResponse]
    comparable: bool
    db_writes: int
    provider_calls: int
    trace_runs_created: int

    @classmethod
    def from_detail(cls, detail: MatchImprovement) -> "MatchImprovementResponse":
        return cls(
            job_id=detail.job_id,
            current_report_id=detail.current_report_id,
            previous_report_id=detail.previous_report_id,
            previous_recommendation=(
                detail.previous_recommendation.value
                if detail.previous_recommendation is not None
                else None
            ),
            current_recommendation=detail.current_recommendation.value,
            previous_profile_version=detail.previous_profile_version,
            current_profile_version=detail.current_profile_version,
            previous_missing_requirement_count=detail.previous_missing_requirement_count,
            current_missing_requirement_count=detail.current_missing_requirement_count,
            resolved_requirement_ids=list(detail.resolved_requirement_ids),
            newly_missing_requirement_ids=list(detail.newly_missing_requirement_ids),
            resolved_requirements=[MatchImprovementRequirementResponse(requirement_id=item.requirement_id, original_text=item.original_text) for item in detail.resolved_requirements],
            newly_missing_requirements=[MatchImprovementRequirementResponse(requirement_id=item.requirement_id, original_text=item.original_text) for item in detail.newly_missing_requirements],
            newly_supporting_evidence=[
                MatchImprovementEvidenceImpactResponse(
                    evidence_id=item.evidence_id,
                    evidence_type=item.evidence_type,
                    summary=item.summary,
                    supporting_requirements=[
                        MatchImprovementRequirementResponse(
                            requirement_id=requirement.requirement_id,
                            original_text=requirement.original_text,
                        )
                        for requirement in item.supporting_requirements
                    ],
                )
                for item in detail.newly_supporting_evidence
            ],
            comparable=detail.comparable,
            db_writes=detail.db_writes,
            provider_calls=detail.provider_calls,
            trace_runs_created=detail.trace_runs_created,
        )

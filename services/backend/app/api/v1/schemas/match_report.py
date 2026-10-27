"""HTTP contracts for persisted MatchReport snapshots and read-only history."""
from __future__ import annotations

from datetime import datetime

from app.api.v1.schemas.common import CamelCaseModel
from app.api.v1.schemas.preference_check import PreferenceCheckResponse
from app.application.match_report import MatchReport


class MatchReportInsightResponse(CamelCaseModel):
    requirement_id: str
    requirement_text: str
    reason: str
    evidence_ids: list[str]


class MatchReportRequirementResponse(CamelCaseModel):
    requirement_id: str
    requirement_index: int
    type: str
    importance: str
    original_text: str
    normalized_capability: str | None
    eligibility_status: str
    semantic_verdict: str
    evidence_ids: list[str]
    profile_fact_refs: list[str]
    reason: str


class MatchEvidenceLinkResponse(CamelCaseModel):
    requirement_id: str
    evidence_ids: list[str]


class JobMatchReportResponse(CamelCaseModel):
    job_id: str
    profile_id: str
    profile_version: int
    extraction_id: str
    search_intent_id: str | None
    search_intent_version: int | None
    preference_checks: list[PreferenceCheckResponse]
    eligibility: str
    recommendation: str
    summary: str
    strengths: list[MatchReportInsightResponse]
    risks: list[MatchReportInsightResponse]
    requirement_results: list[MatchReportRequirementResponse]
    matched_requirement_ids: list[str]
    partial_requirement_ids: list[str]
    missing_requirement_ids: list[str]
    evidence_links: list[MatchEvidenceLinkResponse]
    policy_version: str
    matcher_version: str
    prompt_version: str
    model: str | None
    trace_run_id: str | None
    db_writes: int
    provider_calls: int
    trace_runs_created: int

    @classmethod
    def from_detail(cls, detail: MatchReport) -> "JobMatchReportResponse":
        return cls(
            job_id=detail.job_id,
            profile_id=detail.profile_id,
            profile_version=detail.profile_version,
            extraction_id=detail.extraction_id,
            search_intent_id=detail.search_intent_id,
            search_intent_version=detail.search_intent_version,
            preference_checks=[PreferenceCheckResponse.from_detail(item) for item in detail.preference_checks],
            eligibility=detail.eligibility.value,
            recommendation=detail.recommendation.value,
            summary=detail.summary,
            strengths=[
                MatchReportInsightResponse(
                    requirement_id=item.requirement_id,
                    requirement_text=item.requirement_text,
                    reason=item.reason,
                    evidence_ids=list(item.evidence_ids),
                )
                for item in detail.strengths
            ],
            risks=[
                MatchReportInsightResponse(
                    requirement_id=item.requirement_id,
                    requirement_text=item.requirement_text,
                    reason=item.reason,
                    evidence_ids=list(item.evidence_ids),
                )
                for item in detail.risks
            ],
            requirement_results=[
                MatchReportRequirementResponse(
                    requirement_id=item.requirement_id,
                    requirement_index=item.requirement_index,
                    type=item.type.value,
                    importance=item.importance.value,
                    original_text=item.original_text,
                    normalized_capability=item.normalized_capability,
                    eligibility_status=item.eligibility_status.value,
                    semantic_verdict=item.semantic_verdict.value,
                    evidence_ids=list(item.evidence_ids),
                    profile_fact_refs=list(item.profile_fact_refs),
                    reason=item.reason,
                )
                for item in detail.requirement_results
            ],
            matched_requirement_ids=list(detail.matched_requirement_ids),
            partial_requirement_ids=list(detail.partial_requirement_ids),
            missing_requirement_ids=list(detail.missing_requirement_ids),
            evidence_links=[
                MatchEvidenceLinkResponse(
                    requirement_id=item.requirement_id,
                    evidence_ids=list(item.evidence_ids),
                )
                for item in detail.evidence_links
            ],
            policy_version=detail.policy_version,
            matcher_version=detail.matcher_version,
            prompt_version=detail.prompt_version,
            model=detail.model,
            trace_run_id=detail.trace_run_id,
            db_writes=detail.db_writes,
            provider_calls=detail.provider_calls,
            trace_runs_created=detail.trace_runs_created,
        )


class MatchReportHistoryItemResponse(CamelCaseModel):
    report_id: str
    created_at: datetime
    is_current: bool
    stale_reasons: list[str]
    report: JobMatchReportResponse


class MatchReportHistoryResponse(CamelCaseModel):
    items: list[MatchReportHistoryItemResponse]
    count: int

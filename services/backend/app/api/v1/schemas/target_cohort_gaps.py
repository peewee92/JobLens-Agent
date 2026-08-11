"""HTTP contract for transient Target Cohort Gap Detail projection."""
from __future__ import annotations

from datetime import datetime

from pydantic import Field, model_validator

from app.api.v1.schemas.common import CamelCaseModel
from app.application.target_cohort_candidates import TargetCohortCandidatesResult
from app.application.target_cohort_gap_detail import BuildTargetCohortGapDetailsResult


class TargetCohortCandidateResponse(CamelCaseModel):
    feedback_id: str | None
    job_id: str
    title: str
    company: str
    area: str | None
    salary_min_k: float | None
    salary_max_k: float | None
    decision: str | None
    feedback_created_at: datetime | None
    reasons: list[str]
    note: str | None
    recommendation: str | None
    match_summary: str | None


class TargetCohortCandidatesResponse(CamelCaseModel):
    items: list[TargetCohortCandidateResponse]
    total_job_count: int
    total_feedback_records: int
    latest_job_feedback_count: int
    excluded_rejected_job_count: int
    feedback_overlay_available: bool
    db_writes: int
    provider_calls: int
    trace_runs_created: int

    @classmethod
    def from_result(cls, result: TargetCohortCandidatesResult) -> "TargetCohortCandidatesResponse":
        return cls(
            items=[
                TargetCohortCandidateResponse(
                    feedback_id=item.feedback_id,
                    job_id=item.job_id,
                    title=item.title,
                    company=item.company,
                    area=item.area,
                    salary_min_k=item.salary_min_k,
                    salary_max_k=item.salary_max_k,
                    decision=item.decision.value if item.decision else None,
                    feedback_created_at=item.feedback_created_at,
                    reasons=[reason.value for reason in item.reasons],
                    note=item.note,
                    recommendation=item.recommendation,
                    match_summary=item.match_summary,
                )
                for item in result.items
            ],
            total_job_count=result.total_job_count,
            total_feedback_records=result.total_feedback_records,
            latest_job_feedback_count=result.latest_job_feedback_count,
            excluded_rejected_job_count=result.excluded_rejected_job_count,
            feedback_overlay_available=result.feedback_overlay_available,
            db_writes=result.db_writes,
            provider_calls=result.provider_calls,
            trace_runs_created=result.trace_runs_created,
        )


class TargetCohortGapRequest(CamelCaseModel):
    cohort_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    selected_job_ids: list[str] = Field(default_factory=list, max_length=50)
    selected_feedback_ids: list[str] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def validate_selection_source(self) -> "TargetCohortGapRequest":
        if bool(self.selected_job_ids) == bool(self.selected_feedback_ids):
            raise ValueError("exactly one of selectedJobIds or selectedFeedbackIds is required")
        return self


class TargetCohortGapItemResponse(CamelCaseModel):
    capability: str
    priority: str
    why_important: dict[str, float]
    supporting_requirement_ids: list[str]
    supporting_job_ids: list[str]
    profile_skill_ids: list[str]
    evidence_ids: list[str]
    current_state: str
    completion_criteria: list[str]


class TargetCohortGapResponse(CamelCaseModel):
    cohort_id: str
    job_ids: list[str]
    facts_usable: bool
    profile_id: str | None
    profile_version: int | None
    items: list[TargetCohortGapItemResponse]
    blockers: list[str]
    db_writes: int
    provider_calls: int
    trace_runs_created: int

    @classmethod
    def from_result(cls, result: BuildTargetCohortGapDetailsResult) -> "TargetCohortGapResponse":
        return cls(
            cohort_id=result.cohort_id,
            job_ids=list(result.job_ids),
            facts_usable=result.facts_usable,
            profile_id=result.profile_id,
            profile_version=result.profile_version,
            items=[
                TargetCohortGapItemResponse(
                    capability=item.capability,
                    priority=item.priority.value,
                    why_important=dict(item.why_important),
                    supporting_requirement_ids=list(item.supporting_requirement_ids),
                    supporting_job_ids=list(item.supporting_job_ids),
                    profile_skill_ids=list(item.profile_skill_ids),
                    evidence_ids=list(item.evidence_ids),
                    current_state=item.current_state,
                    completion_criteria=list(item.completion_criteria),
                )
                for item in result.items
            ],
            blockers=list(result.blockers),
            db_writes=result.db_writes,
            provider_calls=result.provider_calls,
            trace_runs_created=result.trace_runs_created,
        )

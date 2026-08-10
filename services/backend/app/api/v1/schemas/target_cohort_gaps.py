"""HTTP contract for transient Target Cohort Gap Detail projection."""
from __future__ import annotations

from pydantic import Field

from app.api.v1.schemas.common import CamelCaseModel
from app.application.target_cohort_gap_detail import BuildTargetCohortGapDetailsResult


class TargetCohortGapRequest(CamelCaseModel):
    cohort_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    selected_feedback_ids: list[str] = Field(min_length=1, max_length=50)


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

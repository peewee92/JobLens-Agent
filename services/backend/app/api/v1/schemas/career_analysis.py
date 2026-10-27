"""Saved analysis contract. Existing Gap/Preparation projections remain unchanged."""
from dataclasses import asdict
from datetime import datetime
from typing import Literal
from app.api.v1.schemas.common import CamelCaseModel
from app.api.v1.schemas.target_cohort_gaps import TargetCohortGapResponse
from app.api.v1.schemas.job_preparation import JobPreparationResponse
from app.application.saved_career_analysis import SavedCareerAnalysis


class AnalysisJobBindingResponse(CamelCaseModel):
    job_id: str
    extraction_id: str
    match_report_id: str
    policy_version: str
    title: str
    company: str


class SavedCareerAnalysisResponse(CamelCaseModel):
    schema_version: Literal[1]
    result_id: str
    thread_id: str
    run_id: str
    created_at: datetime
    profile_id: str
    profile_version: int
    search_intent_id: str
    search_intent_version: int
    selected_job_ids: list[str]
    bindings: list[AnalysisJobBindingResponse]
    gaps: TargetCohortGapResponse
    preparations: list[JobPreparationResponse]
    is_current: bool
    stale_reasons: list[str]
    update_source_thread_id: str | None = None
    update_source_result_id: str | None = None
    update_partial: bool = False
    unanalysed_job_ids: list[str] = []

    @classmethod
    def from_result(cls, result: SavedCareerAnalysis, stale_reasons: tuple[str, ...], update_state=None):
        return cls(schema_version=result.schema_version, result_id=result.result_id,
            thread_id=result.thread_id, run_id=result.run_id, created_at=result.created_at,
            profile_id=result.inputs.profile_id, profile_version=result.inputs.profile_version,
            search_intent_id=result.inputs.search_intent_id, search_intent_version=result.inputs.search_intent_version,
            selected_job_ids=list(result.inputs.selected_job_ids),
            bindings=[AnalysisJobBindingResponse(**asdict(item)) for item in result.bindings],
            gaps=TargetCohortGapResponse.from_result(result.gaps),
            preparations=[JobPreparationResponse.from_result(item) for item in result.preparations],
            is_current=not stale_reasons, stale_reasons=list(stale_reasons),
            update_source_thread_id=update_state.update_source_thread_id if update_state else None,
            update_source_result_id=update_state.update_source_result_id if update_state else None,
            update_partial=update_state.update_partial if update_state else False,
            unanalysed_job_ids=[s.job_id for s in update_state.update_steps if s.status not in {"completed", "reused"}]
                if update_state and update_state.update_partial else [])


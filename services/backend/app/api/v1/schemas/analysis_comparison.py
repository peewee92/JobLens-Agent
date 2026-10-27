from dataclasses import asdict
from typing import Literal
from app.api.v1.schemas.common import CamelCaseModel

Change = Literal['improved', 'weakened', 'unchanged', 'mixed', 'not_comparable', 'unavailable']


class RequirementChangeResponse(CamelCaseModel):
    requirement_id: str
    original_text: str
    previous_coverage: Literal['supported', 'partial', 'unverified', 'hard_conflict']
    current_coverage: Literal['supported', 'partial', 'unverified', 'hard_conflict']
    previous_reason: str
    current_reason: str
    previous_evidence_ids: list[str]
    current_evidence_ids: list[str]
    previous_fact_refs: list[str]
    current_fact_refs: list[str]
    change: Change


class PreferenceChangeResponse(CamelCaseModel):
    key: str
    previous_status: str | None
    current_status: str | None
    previous_code: str | None
    current_code: str | None
    previous_reason: str | None
    current_reason: str | None


class AnalysisJobComparisonResponse(CamelCaseModel):
    job_id: str
    title: str
    previous_report_id: str | None
    current_report_id: str | None
    previous_extraction_id: str | None
    current_extraction_id: str | None
    previous_policy_version: str | None
    current_policy_version: str | None
    previous_recommendation: str | None
    current_recommendation: str | None
    previous_rank: int | None
    current_rank: int | None
    rank_change: int | None
    signal: Change
    recommendation_change: Change
    coverage_change: Change
    reason_codes: list[str]
    requirements: list[RequirementChangeResponse]
    preferences: list[PreferenceChangeResponse]


class AnalysisComparisonResponse(CamelCaseModel):
    comparison_version: Literal[1]
    source_thread_id: str
    source_result_id: str
    thread_id: str
    result_id: str
    scope: Literal['targets', 'batch']
    previous_profile_version: int
    current_profile_version: int
    previous_intent_version: int
    current_intent_version: int
    requested_job_ids: list[str]
    ranking_comparable: bool
    partial: bool
    reason_codes: list[str]
    added_target_ids: list[str]
    removed_target_ids: list[str]
    items: list[AnalysisJobComparisonResponse]

    @classmethod
    def from_result(cls, result):
        return cls.model_validate(asdict(result))

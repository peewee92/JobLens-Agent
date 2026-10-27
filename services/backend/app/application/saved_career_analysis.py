"""One versioned analysis of explicit, released career facts; no model calls."""
from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime, UTC
from enum import Enum
from typing import Literal, Protocol
from uuid import uuid4

from pydantic import TypeAdapter

from app.application.career_context.models import ProfileDetail
from app.application.job_requirements.models import JobRequirementExtractionDetail
from app.application.job_preparation.bundle import BuildJobPreparationBundleUseCase, JobPreparationBundle
from app.application.job_preparation.readiness import JobPreparationReadiness
from app.application.target_cohort_gap_detail import BuildTargetCohortGapDetailsResult
from app.application.target_cohort_gap_query import BuildSelectedFeedbackTargetCohortGapDetailsUseCase
from app.application.target_cohort_requirement_aggregation import AggregateTargetCohortRequirementsUseCase
from app.domain.target_cohort import TargetCohortSnapshot, TargetCohortSelectionSource


class AnalysisFactsChangedError(ValueError):
    """The expected inputs no longer identify current released facts."""


class AnalysisInputsBlockedError(ValueError):
    """Existing readiness or a deterministic workflow cannot provide usable facts."""


@dataclass(frozen=True, slots=True)
class AnalysisFactRequest:
    profile_id: str
    profile_version: int
    search_intent_id: str
    search_intent_version: int
    match_report_ids: tuple[str, ...]
    selected_job_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AnalysisJobBinding:
    job_id: str
    extraction_id: str
    match_report_id: str
    policy_version: str
    title: str
    company: str


@dataclass(frozen=True, slots=True)
class PinnedAnalysisFacts:
    profile: ProfileDetail
    bindings: tuple[AnalysisJobBinding, ...]
    extractions: tuple[JobRequirementExtractionDetail, ...]
    readiness: tuple[JobPreparationReadiness, ...]


@dataclass(frozen=True, slots=True)
class SavedCareerAnalysis:
    schema_version: Literal[1]
    result_id: str
    thread_id: str
    run_id: str
    created_at: datetime
    inputs: AnalysisFactRequest
    bindings: tuple[AnalysisJobBinding, ...]
    gaps: BuildTargetCohortGapDetailsResult
    preparations: tuple[JobPreparationBundle, ...]

    def to_payload(self) -> dict:
        return fact_json(self)

    @classmethod
    def from_payload(cls, value: dict) -> "SavedCareerAnalysis":
        return TypeAdapter(cls).validate_python(value)


def fact_json(value):
    """Serialize immutable mappings without deepcopy, repr, or silent coercion."""
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: fact_json(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {key: fact_json(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [fact_json(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"unsupported analysis fact type: {type(value).__name__}")


class AnalysisFactsReader(Protocol):
    def capture(self, request: AnalysisFactRequest) -> PinnedAnalysisFacts: ...
    def stale_reasons(self, request: AnalysisFactRequest, *, session=None) -> tuple[str, ...]: ...


class BuildSavedCareerAnalysisUseCase:
    def __init__(self, *, facts: AnalysisFactsReader,
                 gaps: BuildSelectedFeedbackTargetCohortGapDetailsUseCase,
                 preparation: BuildJobPreparationBundleUseCase):
        self.facts, self._gaps, self._preparation = facts, gaps, preparation

    def execute(self, *, thread_id: str, run_id: str, request: AnalysisFactRequest) -> SavedCareerAnalysis:
        if not 1 <= len(request.selected_job_ids) <= 5:
            raise AnalysisInputsBlockedError("analysis requires 1..5 confirmed jobs")
        pinned = self.facts.capture(request)
        cohort = TargetCohortSnapshot.create(cohort_id=f"agent_{run_id}",
            name="Career Agent confirmed target cohort", selection_source=TargetCohortSelectionSource.MANUAL,
            job_ids=request.selected_job_ids)
        aggregation = AggregateTargetCohortRequirementsUseCase.from_extractions(cohort, pinned.extractions)
        gaps = self._gaps.execute_from_facts(cohort=cohort, aggregation=aggregation, profile=pinned.profile)
        preparations = tuple(self._preparation.execute_from_facts(
            readiness=readiness, profile=pinned.profile, extraction=extraction,
        ) for readiness, extraction in zip(pinned.readiness, pinned.extractions, strict=True))
        if not gaps.facts_usable or any(not item.facts_usable for item in preparations):
            raise AnalysisInputsBlockedError("analysis workflows returned unusable facts")
        if any(item.provider_calls or item.db_writes for item in (gaps, *preparations)):
            raise AnalysisInputsBlockedError("read-only analysis reported unexpected effects")
        return SavedCareerAnalysis(schema_version=1, result_id=f"analysis_{uuid4().hex}", thread_id=thread_id,
            run_id=run_id, created_at=datetime.now(UTC), inputs=request,
            bindings=pinned.bindings, gaps=gaps, preparations=preparations)

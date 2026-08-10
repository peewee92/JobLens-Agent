"""Read-only aggregation of released JobRequirement facts for a TargetCohort."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.application.job_requirements import JobRequirementExtractionDetail
from app.application.ports.job_requirement_repository import AbstractJobRequirementQueryRepository
from app.domain.job_requirements import RequirementImportance, RequirementType
from app.domain.target_cohort import TargetCohortSnapshot


class RequirementReleaseBlockerLike(Protocol):
    code: object


class RequirementReleaseReadinessLike(Protocol):
    job_id: str
    release_eligible: bool
    extraction_id: str | None
    blockers: tuple[RequirementReleaseBlockerLike, ...]


class RequirementReleaseGate(Protocol):
    def execute(self, job_id: str) -> RequirementReleaseReadinessLike: ...


@dataclass(frozen=True, slots=True)
class TargetCohortRequirementSource:
    job_id: str
    extraction_id: str


@dataclass(frozen=True, slots=True)
class TargetCohortRequirementFact:
    requirement_id: str
    job_id: str
    extraction_id: str
    requirement_index: int
    type: RequirementType
    original_text: str
    normalized_capability: str | None
    importance: RequirementImportance
    evidence_span: str
    confidence: float
    extractor_version: str


@dataclass(frozen=True, slots=True)
class TargetCohortRequirementBlocker:
    job_id: str
    codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TargetCohortRequirementAggregationResult:
    cohort_id: str
    job_ids: tuple[str, ...]
    facts_usable: bool
    sources: tuple[TargetCohortRequirementSource, ...]
    requirements: tuple[TargetCohortRequirementFact, ...]
    blockers: tuple[TargetCohortRequirementBlocker, ...]
    db_writes: int = 0
    provider_calls: int = 0
    trace_runs_created: int = 0


class AggregateTargetCohortRequirementsUseCase:
    """Aggregate only facts that have already passed the Requirement release gate.

    The whole cohort fails closed if any Job is not release-eligible or if the latest
    extraction changes after the release check. Partial cohorts must not silently feed
    downstream Skill Gap statistics.
    """

    def __init__(
        self,
        *,
        release_gate: RequirementReleaseGate,
        requirements: AbstractJobRequirementQueryRepository,
    ) -> None:
        self._release_gate = release_gate
        self._requirements = requirements

    def execute(
        self,
        cohort: TargetCohortSnapshot,
    ) -> TargetCohortRequirementAggregationResult:
        readiness = tuple(self._release_gate.execute(job_id) for job_id in cohort.job_ids)
        release_blockers = tuple(
            TargetCohortRequirementBlocker(
                job_id=item.job_id,
                codes=tuple(str(blocker.code) for blocker in item.blockers),
            )
            for item in readiness
            if not item.release_eligible
        )
        if release_blockers:
            return self._blocked(cohort, release_blockers)

        loaded: list[JobRequirementExtractionDetail] = []
        identity_blockers: list[TargetCohortRequirementBlocker] = []
        for item in readiness:
            extraction = self._requirements.get_latest(item.job_id)
            if extraction is None or extraction.extraction_id != item.extraction_id:
                identity_blockers.append(
                    TargetCohortRequirementBlocker(
                        job_id=item.job_id,
                        codes=("release_identity_changed",),
                    )
                )
                continue
            loaded.append(extraction)

        if identity_blockers:
            return self._blocked(cohort, tuple(identity_blockers))

        sources = tuple(
            TargetCohortRequirementSource(
                job_id=extraction.job_id,
                extraction_id=extraction.extraction_id,
            )
            for extraction in loaded
        )
        facts = tuple(
            TargetCohortRequirementFact(
                requirement_id=requirement.id,
                job_id=requirement.job_id,
                extraction_id=requirement.extraction_id,
                requirement_index=requirement.requirement_index,
                type=requirement.type,
                original_text=requirement.original_text,
                normalized_capability=requirement.normalized_capability,
                importance=requirement.importance,
                evidence_span=requirement.evidence_span,
                confidence=requirement.confidence,
                extractor_version=requirement.extractor_version,
            )
            for extraction in loaded
            for requirement in extraction.requirements
        )
        return TargetCohortRequirementAggregationResult(
            cohort_id=cohort.id,
            job_ids=cohort.job_ids,
            facts_usable=True,
            sources=sources,
            requirements=facts,
            blockers=(),
        )

    @staticmethod
    def _blocked(
        cohort: TargetCohortSnapshot,
        blockers: tuple[TargetCohortRequirementBlocker, ...],
    ) -> TargetCohortRequirementAggregationResult:
        return TargetCohortRequirementAggregationResult(
            cohort_id=cohort.id,
            job_ids=cohort.job_ids,
            facts_usable=False,
            sources=(),
            requirements=(),
            blockers=blockers,
        )


__all__ = [
    "AggregateTargetCohortRequirementsUseCase",
    "TargetCohortRequirementAggregationResult",
    "TargetCohortRequirementBlocker",
    "TargetCohortRequirementFact",
    "TargetCohortRequirementSource",
]

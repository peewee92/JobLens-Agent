"""Deterministic fact candidates for later interview-question generation."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.application.career_context.models import ProfileDetail
from app.application.job_preparation.readiness import JobPreparationReadiness
from app.application.job_preparation.resume_delta import (
    ResumeDeltaFacts,
    ResumeDeltaGapStatus,
)
from app.application.job_requirements.models import JobRequirementExtractionDetail
from app.domain.job_requirements import RequirementImportance, RequirementType


class InterviewPreparationPriority(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class InterviewEvidenceStatus(StrEnum):
    SUPPORTED = "supported"
    UNEVIDENCED = "unevidenced"
    MISSING = "missing"
    NOT_ASSESSED = "not_assessed"


@dataclass(frozen=True, slots=True)
class InterviewQuestionFactItem:
    """One released requirement worth considering during interview preparation.

    This is intentionally a source-fact contract, not a generated question or answer.
    Evidence status is only derived for skill requirements already classified by the
    deterministic Resume Delta fact layer. Other requirement types remain unassessed
    rather than being matched by text or inferred semantics.
    """

    requirement_id: str
    requirement_type: RequirementType
    requirement_text: str
    importance: RequirementImportance
    normalized_capability: str | None
    preparation_priority: InterviewPreparationPriority
    evidence_status: InterviewEvidenceStatus
    profile_skill_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    evidence_summaries: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class InterviewQuestionFacts:
    job_id: str
    facts_usable: bool
    profile_id: str | None
    profile_version: int | None
    extraction_id: str | None
    items: tuple[InterviewQuestionFactItem, ...]
    blockers: tuple[str, ...]
    db_writes: int = 0
    provider_calls: int = 0
    trace_runs_created: int = 0


class BuildInterviewQuestionFactsUseCase:
    """Prioritize released requirements while preserving explicit evidence gaps."""

    _priority_by_importance = {
        RequirementImportance.MUST_HAVE: InterviewPreparationPriority.HIGH,
        RequirementImportance.PREFERRED: InterviewPreparationPriority.MEDIUM,
        RequirementImportance.BONUS: InterviewPreparationPriority.LOW,
    }
    _importance_order = {
        RequirementImportance.MUST_HAVE: 0,
        RequirementImportance.PREFERRED: 1,
        RequirementImportance.BONUS: 2,
    }

    def execute(
        self,
        *,
        readiness: JobPreparationReadiness,
        profile: ProfileDetail,
        extraction: JobRequirementExtractionDetail,
        resume_delta: ResumeDeltaFacts,
    ) -> InterviewQuestionFacts:
        blockers: list[str] = []
        if not readiness.preparation_inputs_ready:
            blockers.append("preparation_inputs_not_ready")
        if readiness.profile_id != profile.id or readiness.profile_version != profile.version:
            blockers.append("profile_identity_changed")
        if (
            readiness.extraction_id != extraction.extraction_id
            or readiness.job_id != extraction.job_id
            or readiness.requirement_count != extraction.requirement_count
        ):
            blockers.append("requirement_identity_changed")
        if not resume_delta.facts_usable:
            blockers.append("resume_delta_not_ready")
        if (
            resume_delta.job_id != readiness.job_id
            or resume_delta.profile_id != readiness.profile_id
            or resume_delta.profile_version != readiness.profile_version
            or resume_delta.extraction_id != readiness.extraction_id
        ):
            blockers.append("resume_delta_identity_changed")

        if blockers:
            return self._blocked(readiness.job_id, blockers)

        highlights = {item.requirement_id: item for item in resume_delta.highlights}
        gaps = {item.requirement_id: item for item in resume_delta.evidence_gaps}
        evidence_by_id = {item.id: item for item in profile.evidence}

        indexed_requirements = list(enumerate(extraction.requirements))
        indexed_requirements.sort(
            key=lambda pair: (self._importance_order[pair[1].importance], pair[0])
        )

        items: list[InterviewQuestionFactItem] = []
        for _, requirement in indexed_requirements:
            evidence_status = InterviewEvidenceStatus.NOT_ASSESSED
            profile_skill_ids: tuple[str, ...] = ()
            evidence_ids: tuple[str, ...] = ()
            evidence_summaries: tuple[str, ...] = ()

            if requirement.type is RequirementType.SKILL:
                highlight = highlights.get(requirement.id)
                gap = gaps.get(requirement.id)
                if highlight is not None and gap is not None:
                    return self._blocked(
                        readiness.job_id,
                        ["resume_delta_provenance_invalid"],
                    )
                if highlight is not None:
                    source_evidence = tuple(
                        evidence_by_id.get(evidence_id) for evidence_id in highlight.evidence_ids
                    )
                    if any(evidence is None for evidence in source_evidence):
                        return self._blocked(
                            readiness.job_id,
                            ["resume_delta_provenance_invalid"],
                        )
                    evidence_status = InterviewEvidenceStatus.SUPPORTED
                    profile_skill_ids = highlight.profile_skill_ids
                    evidence_ids = highlight.evidence_ids
                    evidence_summaries = tuple(
                        evidence.summary
                        for evidence in source_evidence
                        if evidence is not None
                    )
                elif gap is not None:
                    profile_skill_ids = gap.profile_skill_ids
                    evidence_status = (
                        InterviewEvidenceStatus.UNEVIDENCED
                        if gap.status is ResumeDeltaGapStatus.UNEVIDENCED
                        else InterviewEvidenceStatus.MISSING
                    )

            items.append(
                InterviewQuestionFactItem(
                    requirement_id=requirement.id,
                    requirement_type=requirement.type,
                    requirement_text=requirement.original_text,
                    importance=requirement.importance,
                    normalized_capability=requirement.normalized_capability,
                    preparation_priority=self._priority_by_importance[requirement.importance],
                    evidence_status=evidence_status,
                    profile_skill_ids=profile_skill_ids,
                    evidence_ids=evidence_ids,
                    evidence_summaries=evidence_summaries,
                )
            )

        return InterviewQuestionFacts(
            job_id=readiness.job_id,
            facts_usable=True,
            profile_id=profile.id,
            profile_version=profile.version,
            extraction_id=extraction.extraction_id,
            items=tuple(items),
            blockers=(),
        )

    @staticmethod
    def _blocked(job_id: str, blockers: list[str]) -> InterviewQuestionFacts:
        return InterviewQuestionFacts(
            job_id=job_id,
            facts_usable=False,
            profile_id=None,
            profile_version=None,
            extraction_id=None,
            items=(),
            blockers=tuple(dict.fromkeys(blockers)),
        )


__all__ = [
    "BuildInterviewQuestionFactsUseCase",
    "InterviewEvidenceStatus",
    "InterviewPreparationPriority",
    "InterviewQuestionFactItem",
    "InterviewQuestionFacts",
]

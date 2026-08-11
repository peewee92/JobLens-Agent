"""Deterministic fact selection for STAR/project storytelling preparation."""
from __future__ import annotations

from dataclasses import dataclass

from app.application.career_context.models import ProfileDetail
from app.application.job_preparation.experience_priority import ExperiencePriorityFacts
from app.application.job_preparation.readiness import JobPreparationReadiness
from app.application.job_requirements.models import JobRequirementExtractionDetail
from app.domain.career_context import EvidenceType


@dataclass(frozen=True, slots=True)
class StoryFactSelectionItem:
    """Confirmed source facts that may safely anchor a later project story.

    This contract intentionally does not contain synthesized STAR fields, metrics,
    responsibilities, or outcomes. Later generation may only transform these facts
    under its own evidence-preservation checks.
    """

    evidence_id: str
    evidence_type: EvidenceType
    evidence_summary: str
    supporting_requirement_ids: tuple[str, ...]
    supporting_requirement_texts: tuple[str, ...]
    matched_capabilities: tuple[str, ...]
    must_have_count: int
    requirement_count: int


@dataclass(frozen=True, slots=True)
class StoryFactSelection:
    job_id: str
    facts_usable: bool
    profile_id: str | None
    profile_version: int | None
    extraction_id: str | None
    items: tuple[StoryFactSelectionItem, ...]
    blockers: tuple[str, ...]
    db_writes: int = 0
    provider_calls: int = 0
    trace_runs_created: int = 0


class BuildStoryFactSelectionUseCase:
    """Select only confirmed prioritized Evidence and released Requirement facts."""

    def execute(
        self,
        *,
        readiness: JobPreparationReadiness,
        profile: ProfileDetail,
        extraction: JobRequirementExtractionDetail,
        priority: ExperiencePriorityFacts,
    ) -> StoryFactSelection:
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
        if not priority.facts_usable:
            blockers.append("experience_priority_not_ready")
        if (
            priority.job_id != readiness.job_id
            or priority.profile_id != readiness.profile_id
            or priority.profile_version != readiness.profile_version
            or priority.extraction_id != readiness.extraction_id
        ):
            blockers.append("experience_priority_identity_changed")

        if blockers:
            return self._blocked(readiness.job_id, blockers)

        evidence_by_id = {evidence.id: evidence for evidence in profile.evidence}
        requirement_by_id = {
            requirement.id: requirement for requirement in extraction.requirements
        }
        items: list[StoryFactSelectionItem] = []

        for priority_item in priority.items:
            evidence = evidence_by_id.get(priority_item.evidence_id)
            requirements = tuple(
                requirement_by_id.get(requirement_id)
                for requirement_id in priority_item.supporting_requirement_ids
            )
            if (
                evidence is None
                or evidence.type != priority_item.evidence_type
                or evidence.type not in (EvidenceType.PROJECT, EvidenceType.WORK)
                or any(requirement is None for requirement in requirements)
            ):
                return self._blocked(
                    readiness.job_id,
                    ["experience_priority_provenance_invalid"],
                )

            items.append(
                StoryFactSelectionItem(
                    evidence_id=evidence.id,
                    evidence_type=evidence.type,
                    evidence_summary=evidence.summary,
                    supporting_requirement_ids=priority_item.supporting_requirement_ids,
                    supporting_requirement_texts=tuple(
                        requirement.original_text
                        for requirement in requirements
                        if requirement is not None
                    ),
                    matched_capabilities=priority_item.matched_capabilities,
                    must_have_count=priority_item.must_have_count,
                    requirement_count=priority_item.requirement_count,
                )
            )

        return StoryFactSelection(
            job_id=readiness.job_id,
            facts_usable=True,
            profile_id=profile.id,
            profile_version=profile.version,
            extraction_id=extraction.extraction_id,
            items=tuple(items),
            blockers=(),
        )

    @staticmethod
    def _blocked(job_id: str, blockers: list[str]) -> StoryFactSelection:
        return StoryFactSelection(
            job_id=job_id,
            facts_usable=False,
            profile_id=None,
            profile_version=None,
            extraction_id=None,
            items=(),
            blockers=tuple(dict.fromkeys(blockers)),
        )


__all__ = [
    "BuildStoryFactSelectionUseCase",
    "StoryFactSelection",
    "StoryFactSelectionItem",
]

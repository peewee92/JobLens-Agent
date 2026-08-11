"""Deterministic project/work evidence prioritization for one trusted job."""
from __future__ import annotations

from dataclasses import dataclass

from app.application.career_context.models import ProfileDetail
from app.application.job_preparation.readiness import JobPreparationReadiness
from app.application.job_requirements.models import JobRequirementExtractionDetail
from app.application.target_cohort_capability_normalization import (
    canonicalize_target_cohort_capability,
)
from app.domain.career_context import EvidenceType
from app.domain.job_requirements import RequirementImportance, RequirementType


@dataclass(frozen=True, slots=True)
class ExperiencePriorityItem:
    evidence_id: str
    evidence_type: EvidenceType
    supporting_requirement_ids: tuple[str, ...]
    matched_capabilities: tuple[str, ...]
    must_have_count: int
    requirement_count: int


@dataclass(frozen=True, slots=True)
class ExperiencePriorityFacts:
    job_id: str
    facts_usable: bool
    profile_id: str | None
    profile_version: int | None
    extraction_id: str | None
    items: tuple[ExperiencePriorityItem, ...]
    blockers: tuple[str, ...]
    db_writes: int = 0
    provider_calls: int = 0
    trace_runs_created: int = 0


class BuildExperiencePriorityUseCase:
    """Rank confirmed project/work Evidence only by explicit skill links.

    Evidence prose is never searched for relevance here. A project or work item is
    included only when a confirmed Profile Skill links that Evidence and the same
    skill exactly matches a released skill Requirement after explicit capability
    alias normalization. Sorting favors must-have coverage, then total requirement
    coverage, while preserving Profile Evidence order as the deterministic tie-break.
    """

    def execute(
        self,
        *,
        readiness: JobPreparationReadiness,
        profile: ProfileDetail,
        extraction: JobRequirementExtractionDetail,
    ) -> ExperiencePriorityFacts:
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

        if blockers:
            return ExperiencePriorityFacts(
                job_id=readiness.job_id,
                facts_usable=False,
                profile_id=None,
                profile_version=None,
                extraction_id=None,
                items=(),
                blockers=tuple(dict.fromkeys(blockers)),
            )

        evidence_by_id = {
            evidence.id: evidence
            for evidence in profile.evidence
            if evidence.type in (EvidenceType.PROJECT, EvidenceType.WORK)
        }
        evidence_order = {
            evidence.id: index
            for index, evidence in enumerate(profile.evidence)
            if evidence.id in evidence_by_id
        }

        evidence_capabilities: dict[str, set[str]] = {}
        for skill in profile.skills:
            capability = canonicalize_target_cohort_capability(skill.name)
            if not capability:
                continue
            for evidence_id in skill.evidence_ids:
                if evidence_id in evidence_by_id:
                    evidence_capabilities.setdefault(evidence_id, set()).add(capability)

        normalized_requirements: list[tuple[object, str]] = []
        for requirement in extraction.requirements:
            if requirement.type is not RequirementType.SKILL:
                continue
            capability = canonicalize_target_cohort_capability(
                requirement.normalized_capability or ""
            )
            if capability:
                normalized_requirements.append((requirement, capability))

        items: list[ExperiencePriorityItem] = []
        for evidence_id, capabilities in evidence_capabilities.items():
            matched_requirements = [
                requirement
                for requirement, capability in normalized_requirements
                if capability in capabilities
            ]
            if not matched_requirements:
                continue
            matched_capabilities = tuple(
                dict.fromkeys(
                    canonicalize_target_cohort_capability(
                        requirement.normalized_capability or ""
                    )
                    for requirement in matched_requirements
                )
            )
            items.append(
                ExperiencePriorityItem(
                    evidence_id=evidence_id,
                    evidence_type=evidence_by_id[evidence_id].type,
                    supporting_requirement_ids=tuple(
                        dict.fromkeys(requirement.id for requirement in matched_requirements)
                    ),
                    matched_capabilities=matched_capabilities,
                    must_have_count=sum(
                        requirement.importance is RequirementImportance.MUST_HAVE
                        for requirement in matched_requirements
                    ),
                    requirement_count=len(matched_requirements),
                )
            )

        items.sort(
            key=lambda item: (
                -item.must_have_count,
                -item.requirement_count,
                evidence_order[item.evidence_id],
            )
        )
        return ExperiencePriorityFacts(
            job_id=readiness.job_id,
            facts_usable=True,
            profile_id=profile.id,
            profile_version=profile.version,
            extraction_id=extraction.extraction_id,
            items=tuple(items),
            blockers=(),
        )


__all__ = [
    "BuildExperiencePriorityUseCase",
    "ExperiencePriorityFacts",
    "ExperiencePriorityItem",
]

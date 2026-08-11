"""Deterministic Resume Delta facts for one trusted job/profile pair."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.application.career_context.models import ProfileDetail
from app.application.job_preparation.readiness import JobPreparationReadiness
from app.application.job_requirements.models import JobRequirementExtractionDetail
from app.application.target_cohort_capability_normalization import (
    canonicalize_target_cohort_capability,
)
from app.domain.job_requirements import RequirementType


class ResumeDeltaGapStatus(StrEnum):
    UNEVIDENCED = "unevidenced"
    MISSING = "missing"


@dataclass(frozen=True, slots=True)
class ResumeDeltaHighlight:
    requirement_id: str
    capability: str
    profile_skill_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ResumeDeltaEvidenceGap:
    requirement_id: str
    capability: str
    status: ResumeDeltaGapStatus
    profile_skill_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ResumeDeltaFacts:
    job_id: str
    facts_usable: bool
    profile_id: str | None
    profile_version: int | None
    extraction_id: str | None
    highlights: tuple[ResumeDeltaHighlight, ...]
    evidence_gaps: tuple[ResumeDeltaEvidenceGap, ...]
    blockers: tuple[str, ...]
    db_writes: int = 0
    provider_calls: int = 0
    trace_runs_created: int = 0


class BuildResumeDeltaFactsUseCase:
    """Project only facts safe to use for later resume-adjustment suggestions.

    This layer never writes resume copy. A requirement is highlightable only when an
    explicit Profile skill matches the normalized requirement capability and that
    skill links to confirmed Evidence. Skill-name-only matches are exposed as
    unevidenced gaps; absent skills are missing gaps. Non-skill requirements are
    intentionally deferred to later preparation slices rather than guessed here.
    """

    def execute(
        self,
        *,
        readiness: JobPreparationReadiness,
        profile: ProfileDetail,
        extraction: JobRequirementExtractionDetail,
    ) -> ResumeDeltaFacts:
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
            return ResumeDeltaFacts(
                job_id=readiness.job_id,
                facts_usable=False,
                profile_id=None,
                profile_version=None,
                extraction_id=None,
                highlights=(),
                evidence_gaps=(),
                blockers=tuple(dict.fromkeys(blockers)),
            )

        skills_by_capability: dict[str, list[tuple[str, tuple[str, ...]]]] = {}
        for skill in profile.skills:
            capability = canonicalize_target_cohort_capability(skill.name)
            if capability:
                skills_by_capability.setdefault(capability, []).append(
                    (skill.id, skill.evidence_ids)
                )

        highlights: list[ResumeDeltaHighlight] = []
        evidence_gaps: list[ResumeDeltaEvidenceGap] = []
        for requirement in extraction.requirements:
            if requirement.type is not RequirementType.SKILL:
                continue
            capability = canonicalize_target_cohort_capability(
                requirement.normalized_capability or ""
            )
            if not capability:
                continue

            matched_skills = skills_by_capability.get(capability, [])
            skill_ids = tuple(skill_id for skill_id, _ in matched_skills)
            evidence_ids = tuple(
                dict.fromkeys(
                    evidence_id
                    for _, ids in matched_skills
                    for evidence_id in ids
                )
            )
            if evidence_ids:
                highlights.append(
                    ResumeDeltaHighlight(
                        requirement_id=requirement.id,
                        capability=capability,
                        profile_skill_ids=skill_ids,
                        evidence_ids=evidence_ids,
                    )
                )
            else:
                evidence_gaps.append(
                    ResumeDeltaEvidenceGap(
                        requirement_id=requirement.id,
                        capability=capability,
                        status=(
                            ResumeDeltaGapStatus.UNEVIDENCED
                            if skill_ids
                            else ResumeDeltaGapStatus.MISSING
                        ),
                        profile_skill_ids=skill_ids,
                    )
                )

        return ResumeDeltaFacts(
            job_id=readiness.job_id,
            facts_usable=True,
            profile_id=profile.id,
            profile_version=profile.version,
            extraction_id=extraction.extraction_id,
            highlights=tuple(highlights),
            evidence_gaps=tuple(evidence_gaps),
            blockers=(),
        )


__all__ = [
    "BuildResumeDeltaFactsUseCase",
    "ResumeDeltaEvidenceGap",
    "ResumeDeltaFacts",
    "ResumeDeltaGapStatus",
    "ResumeDeltaHighlight",
]

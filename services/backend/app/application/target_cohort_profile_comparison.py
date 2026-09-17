"""Deterministic market-capability versus confirmed Profile fact comparison."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.application.career_context.models import ProfileDetail
from app.application.target_cohort_capability_normalization import (
    TargetCohortCapabilityNormalizationResult,
    canonicalize_target_cohort_capability,
)


class ProfileCapabilityCoverageStatus(StrEnum):
    EVIDENCED = "evidenced"
    UNEVIDENCED = "unevidenced"
    MISSING = "missing"


@dataclass(frozen=True, slots=True)
class TargetCohortProfileCapabilityComparison:
    capability: str
    status: ProfileCapabilityCoverageStatus
    requirement_ids: tuple[str, ...]
    job_ids: tuple[str, ...]
    requirement_count: int
    job_count: int
    must_have_count: int
    preferred_count: int
    bonus_count: int
    profile_skill_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TargetCohortProfileComparisonResult:
    cohort_id: str
    job_ids: tuple[str, ...]
    facts_usable: bool
    profile_id: str | None
    profile_version: int | None
    capabilities: tuple[TargetCohortProfileCapabilityComparison, ...]
    db_writes: int = 0
    provider_calls: int = 0
    trace_runs_created: int = 0


class CompareTargetCohortCapabilitiesToProfileUseCase:
    """Compare released market skill facts with explicit Profile skills only.

    A Profile skill is treated as evidenced only when it carries explicit Evidence
    references. No fuzzy matching or semantic inference is used here; aliases share
    the same explicit canonicalization policy as TargetCohort normalization.
    """

    def execute(
        self,
        market: TargetCohortCapabilityNormalizationResult,
        profile: ProfileDetail,
    ) -> TargetCohortProfileComparisonResult:
        if not market.facts_usable:
            return TargetCohortProfileComparisonResult(
                cohort_id=market.cohort_id,
                job_ids=market.job_ids,
                facts_usable=False,
                profile_id=profile.id,
                profile_version=profile.version,
                capabilities=(),
            )

        skills_by_capability: dict[str, list[tuple[str, tuple[str, ...]]]] = {}
        for skill in profile.skills:
            canonical = canonicalize_target_cohort_capability(skill.name)
            if not canonical:
                continue
            skills_by_capability.setdefault(canonical, []).append(
                (skill.id, skill.evidence_ids)
            )

        comparisons: list[TargetCohortProfileCapabilityComparison] = []
        for capability in market.capabilities:
            matched_skills = list(skills_by_capability.get(capability.capability, []))
            if not matched_skills and capability.member_options:
                for member in capability.member_options:
                    matched_skills.extend(skills_by_capability.get(member, []))
                matched_skills = list(dict.fromkeys(matched_skills))
            skill_ids = tuple(item[0] for item in matched_skills)
            evidence_ids = tuple(
                dict.fromkeys(
                    evidence_id
                    for _, ids in matched_skills
                    for evidence_id in ids
                )
            )
            if evidence_ids:
                status = ProfileCapabilityCoverageStatus.EVIDENCED
            elif skill_ids:
                status = ProfileCapabilityCoverageStatus.UNEVIDENCED
            else:
                status = ProfileCapabilityCoverageStatus.MISSING

            comparisons.append(
                TargetCohortProfileCapabilityComparison(
                    capability=capability.capability,
                    status=status,
                    requirement_ids=capability.requirement_ids,
                    job_ids=capability.job_ids,
                    requirement_count=capability.requirement_count,
                    job_count=capability.job_count,
                    must_have_count=capability.must_have_count,
                    preferred_count=capability.preferred_count,
                    bonus_count=capability.bonus_count,
                    profile_skill_ids=skill_ids,
                    evidence_ids=evidence_ids,
                )
            )

        return TargetCohortProfileComparisonResult(
            cohort_id=market.cohort_id,
            job_ids=market.job_ids,
            facts_usable=True,
            profile_id=profile.id,
            profile_version=profile.version,
            capabilities=tuple(comparisons),
        )


__all__ = [
    "CompareTargetCohortCapabilitiesToProfileUseCase",
    "ProfileCapabilityCoverageStatus",
    "TargetCohortProfileCapabilityComparison",
    "TargetCohortProfileComparisonResult",
]

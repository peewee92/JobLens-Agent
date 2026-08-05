"""Read-only release policy for confirmed career-context facts.

The Match phase may consume only explicit, versioned user confirmations. LLM
Profile proposals and Profile Eval baselines remain separate governance facts;
they never replace confirmation of the current UserProfile/SearchIntent.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.application.career_context.models import ProfileDetail, SearchIntentDetail
from app.application.ports.career_context_repository import (
    AbstractCareerContextQueryRepository,
)


class CareerContextReleaseBlockerCode(StrEnum):
    PROFILE_MISSING = "profile_missing"
    PROFILE_HEADLINE_MISSING = "profile_headline_missing"
    PROFILE_YEARS_INVALID = "profile_years_invalid"
    PROFILE_EVIDENCE_MISSING = "profile_evidence_missing"
    PROFILE_EVIDENCE_INVALID = "profile_evidence_invalid"
    PROFILE_EVIDENCE_KEYS_DUPLICATED = "profile_evidence_keys_duplicated"
    PROFILE_SKILLS_MISSING = "profile_skills_missing"
    PROFILE_SKILL_NAMES_DUPLICATED = "profile_skill_names_duplicated"
    PROFILE_SKILL_EVIDENCE_MISSING = "profile_skill_evidence_missing"
    PROFILE_SKILL_EVIDENCE_REFERENCE_INVALID = (
        "profile_skill_evidence_reference_invalid"
    )
    SEARCH_INTENT_MISSING = "search_intent_missing"
    SEARCH_INTENT_TARGET_ROLES_MISSING = "search_intent_target_roles_missing"
    SEARCH_INTENT_TARGET_ROLES_DUPLICATED = (
        "search_intent_target_roles_duplicated"
    )
    SEARCH_INTENT_MINIMUM_SALARY_INVALID = (
        "search_intent_minimum_salary_invalid"
    )


@dataclass(frozen=True, slots=True)
class CareerContextReleaseBlocker:
    code: CareerContextReleaseBlockerCode
    message: str


@dataclass(frozen=True, slots=True)
class CareerContextReleaseReadiness:
    release_eligible: bool
    confirmation_boundary: str
    profile_id: str | None
    profile_version: int | None
    profile_created_at: datetime | None
    profile_evidence_count: int
    profile_skill_count: int
    search_intent_id: str | None
    search_intent_version: int | None
    search_intent_created_at: datetime | None
    search_intent_target_role_count: int
    blockers: tuple[CareerContextReleaseBlocker, ...]


class GetCareerContextReleaseReadinessUseCase:
    """Derive whether confirmed Profile + SearchIntent may feed future Match.

    This query does not call an LLM, inspect Profile Eval baselines, write data,
    or generate a Trace. It validates only the latest explicitly confirmed
    versions and their deterministic evidence/reference invariants.
    """

    def __init__(self, repository: AbstractCareerContextQueryRepository) -> None:
        self._repository = repository

    def execute(self) -> CareerContextReleaseReadiness:
        snapshot = self._repository.get_current_context()
        profile = snapshot.profile
        intent = snapshot.search_intent
        blockers = [
            *self._profile_blockers(profile),
            *self._search_intent_blockers(intent),
        ]
        return CareerContextReleaseReadiness(
            release_eligible=not blockers,
            confirmation_boundary="explicit_versioned_user_confirmation",
            profile_id=profile.id if profile is not None else None,
            profile_version=profile.version if profile is not None else None,
            profile_created_at=profile.created_at if profile is not None else None,
            profile_evidence_count=len(profile.evidence) if profile is not None else 0,
            profile_skill_count=len(profile.skills) if profile is not None else 0,
            search_intent_id=intent.id if intent is not None else None,
            search_intent_version=intent.version if intent is not None else None,
            search_intent_created_at=(
                intent.created_at if intent is not None else None
            ),
            search_intent_target_role_count=(
                len(intent.target_roles) if intent is not None else 0
            ),
            blockers=tuple(blockers),
        )

    @staticmethod
    def _profile_blockers(
        profile: ProfileDetail | None,
    ) -> tuple[CareerContextReleaseBlocker, ...]:
        if profile is None:
            return (
                CareerContextReleaseBlocker(
                    code=CareerContextReleaseBlockerCode.PROFILE_MISSING,
                    message=(
                        "Confirm a UserProfile version before Match consumes "
                        "career facts."
                    ),
                ),
            )

        blockers: list[CareerContextReleaseBlocker] = []
        if not profile.headline.strip():
            blockers.append(
                CareerContextReleaseBlocker(
                    code=CareerContextReleaseBlockerCode.PROFILE_HEADLINE_MISSING,
                    message="The confirmed Profile headline is blank.",
                )
            )
        if (
            profile.years_of_experience is not None
            and profile.years_of_experience < 0
        ):
            blockers.append(
                CareerContextReleaseBlocker(
                    code=CareerContextReleaseBlockerCode.PROFILE_YEARS_INVALID,
                    message="The confirmed Profile has negative experience years.",
                )
            )

        if not profile.evidence:
            blockers.append(
                CareerContextReleaseBlocker(
                    code=CareerContextReleaseBlockerCode.PROFILE_EVIDENCE_MISSING,
                    message=(
                        "Add at least one confirmed Evidence item before Match "
                        "uses the Profile."
                    ),
                )
            )
        invalid_evidence = [
            item.key or item.id
            for item in profile.evidence
            if not item.key.strip()
            or not item.summary.strip()
            or not item.source.strip()
        ]
        if invalid_evidence:
            blockers.append(
                CareerContextReleaseBlocker(
                    code=CareerContextReleaseBlockerCode.PROFILE_EVIDENCE_INVALID,
                    message=(
                        "Confirmed Evidence contains blank key, summary, or source: "
                        + ", ".join(invalid_evidence)
                    ),
                )
            )
        evidence_keys = [item.key.strip().casefold() for item in profile.evidence]
        if len(set(evidence_keys)) != len(evidence_keys):
            blockers.append(
                CareerContextReleaseBlocker(
                    code=(
                        CareerContextReleaseBlockerCode.PROFILE_EVIDENCE_KEYS_DUPLICATED
                    ),
                    message="Confirmed Evidence keys are duplicated.",
                )
            )

        if not profile.skills:
            blockers.append(
                CareerContextReleaseBlocker(
                    code=CareerContextReleaseBlockerCode.PROFILE_SKILLS_MISSING,
                    message=(
                        "Add at least one confirmed Skill with Evidence before "
                        "Match uses the Profile."
                    ),
                )
            )
        skill_names = [item.name.strip().casefold() for item in profile.skills]
        if len(set(skill_names)) != len(skill_names):
            blockers.append(
                CareerContextReleaseBlocker(
                    code=(
                        CareerContextReleaseBlockerCode.PROFILE_SKILL_NAMES_DUPLICATED
                    ),
                    message="Confirmed Skill names are duplicated.",
                )
            )

        skills_without_evidence = [
            item.name for item in profile.skills if not item.evidence_ids
        ]
        if skills_without_evidence:
            blockers.append(
                CareerContextReleaseBlocker(
                    code=(
                        CareerContextReleaseBlockerCode.PROFILE_SKILL_EVIDENCE_MISSING
                    ),
                    message=(
                        "Confirmed Skills must link to Evidence: "
                        + ", ".join(skills_without_evidence)
                    ),
                )
            )
        evidence_ids = {item.id for item in profile.evidence}
        invalid_skill_refs = [
            item.name
            for item in profile.skills
            if any(evidence_id not in evidence_ids for evidence_id in item.evidence_ids)
        ]
        if invalid_skill_refs:
            blockers.append(
                CareerContextReleaseBlocker(
                    code=(
                        CareerContextReleaseBlockerCode.PROFILE_SKILL_EVIDENCE_REFERENCE_INVALID
                    ),
                    message=(
                        "Confirmed Skills reference missing Evidence rows: "
                        + ", ".join(invalid_skill_refs)
                    ),
                )
            )
        return tuple(blockers)

    @staticmethod
    def _search_intent_blockers(
        intent: SearchIntentDetail | None,
    ) -> tuple[CareerContextReleaseBlocker, ...]:
        if intent is None:
            return (
                CareerContextReleaseBlocker(
                    code=CareerContextReleaseBlockerCode.SEARCH_INTENT_MISSING,
                    message=(
                        "Confirm a SearchIntent version before Match evaluates "
                        "job fit."
                    ),
                ),
            )

        blockers: list[CareerContextReleaseBlocker] = []
        normalized_roles = [
            role.strip().casefold() for role in intent.target_roles if role.strip()
        ]
        if not normalized_roles:
            blockers.append(
                CareerContextReleaseBlocker(
                    code=(
                        CareerContextReleaseBlockerCode.SEARCH_INTENT_TARGET_ROLES_MISSING
                    ),
                    message="The confirmed SearchIntent has no target role.",
                )
            )
        elif len(set(normalized_roles)) != len(normalized_roles):
            blockers.append(
                CareerContextReleaseBlocker(
                    code=(
                        CareerContextReleaseBlockerCode.SEARCH_INTENT_TARGET_ROLES_DUPLICATED
                    ),
                    message="Confirmed target roles are duplicated.",
                )
            )
        if intent.minimum_salary_k is not None and intent.minimum_salary_k < 0:
            blockers.append(
                CareerContextReleaseBlocker(
                    code=(
                        CareerContextReleaseBlockerCode.SEARCH_INTENT_MINIMUM_SALARY_INVALID
                    ),
                    message="The confirmed minimum salary is negative.",
                )
            )
        return tuple(blockers)

"""Deterministic release policy tests for confirmed career context."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from app.application.career_context.models import (
    CareerContextSnapshot,
    EvidenceDetail,
    ProfileDetail,
    SearchIntentDetail,
    SkillDetail,
)
from app.application.career_context.release import (
    CareerContextReleaseBlockerCode,
    GetCareerContextReleaseReadinessUseCase,
)
from app.domain.career_context import EvidenceType, Seniority, SkillLevel

NOW = datetime(2026, 8, 5, 10, 0, tzinfo=timezone.utc)


class FakeCareerContextQueryRepository:
    def __init__(
        self,
        *,
        profile: ProfileDetail | None,
        intent: SearchIntentDetail | None,
    ) -> None:
        self.profile = profile
        self.intent = intent

    def get_current_context(self) -> CareerContextSnapshot:
        return CareerContextSnapshot(
            profile=self.profile,
            search_intent=self.intent,
        )

    def get_current_profile(self) -> ProfileDetail | None:
        raise AssertionError("release policy must use one atomic context snapshot")

    def get_current_search_intent(self) -> SearchIntentDetail | None:
        raise AssertionError("release policy must use one atomic context snapshot")


def _profile() -> ProfileDetail:
    evidence = (
        EvidenceDetail(
            id="evi_1",
            key="spinach-desktop",
            type=EvidenceType.WORK,
            summary="Built Electron and Agent collaboration features.",
            source="confirmed by user",
        ),
        EvidenceDetail(
            id="evi_2",
            key="joblens",
            type=EvidenceType.PROJECT,
            summary="Built a FastAPI and Next.js evidence-based job tool.",
            source="confirmed by user",
        ),
    )
    return ProfileDetail(
        id="prof_3",
        version=3,
        headline="Frontend Engineer moving into Agent application engineering",
        years_of_experience=8,
        evidence=evidence,
        skills=(
            SkillDetail(
                id="skill_1",
                name="React",
                level=SkillLevel.STRONG,
                evidence_ids=("evi_1",),
            ),
            SkillDetail(
                id="skill_2",
                name="Agent Application Engineering",
                level=SkillLevel.WORKING,
                evidence_ids=("evi_1", "evi_2"),
            ),
        ),
        created_at=NOW,
    )


def _intent() -> SearchIntentDetail:
    return SearchIntentDetail(
        id="intent_2",
        version=2,
        target_roles=("Agent Engineer", "AI Application Engineer"),
        cities=("武汉",),
        remote_accepted=True,
        minimum_salary_k=20,
        seniority=Seniority.SENIOR,
        employment_types=("full_time",),
        exclude_keywords=("博彩",),
        hard_constraints=("不接受长期驻场",),
        soft_preferences=("AI 产品有真实用户",),
        created_at=NOW,
    )


def _execute(
    profile: ProfileDetail | None,
    intent: SearchIntentDetail | None,
):
    return GetCareerContextReleaseReadinessUseCase(
        FakeCareerContextQueryRepository(profile=profile, intent=intent)
    ).execute()


def _codes(result) -> set[CareerContextReleaseBlockerCode]:
    return {item.code for item in result.blockers}


def test_missing_confirmed_versions_fail_closed_with_distinct_blockers() -> None:
    result = _execute(None, None)

    assert result.release_eligible is False
    assert _codes(result) == {
        CareerContextReleaseBlockerCode.PROFILE_MISSING,
        CareerContextReleaseBlockerCode.SEARCH_INTENT_MISSING,
    }
    assert result.profile_id is None
    assert result.search_intent_id is None
    assert result.profile_evidence_count == 0
    assert result.search_intent_target_role_count == 0


def test_complete_confirmed_versions_release_without_profile_eval_baseline() -> None:
    result = _execute(_profile(), _intent())

    assert result.release_eligible is True
    assert result.confirmation_boundary == "explicit_versioned_user_confirmation"
    assert result.profile_id == "prof_3"
    assert result.profile_version == 3
    assert result.profile_evidence_count == 2
    assert result.profile_skill_count == 2
    assert result.search_intent_id == "intent_2"
    assert result.search_intent_version == 2
    assert result.search_intent_target_role_count == 2
    assert result.blockers == ()


def test_empty_confirmed_profile_is_not_match_ready() -> None:
    profile = replace(
        _profile(),
        headline="   ",
        years_of_experience=-1,
        evidence=(),
        skills=(),
    )

    result = _execute(profile, _intent())

    assert result.release_eligible is False
    assert _codes(result) == {
        CareerContextReleaseBlockerCode.PROFILE_HEADLINE_MISSING,
        CareerContextReleaseBlockerCode.PROFILE_YEARS_INVALID,
        CareerContextReleaseBlockerCode.PROFILE_EVIDENCE_MISSING,
        CareerContextReleaseBlockerCode.PROFILE_SKILLS_MISSING,
    }


def test_corrupted_profile_evidence_and_skill_links_fail_closed() -> None:
    profile = _profile()
    corrupted = replace(
        profile,
        evidence=(
            replace(profile.evidence[0], summary=" "),
            replace(profile.evidence[1], key="SPINACH-DESKTOP"),
        ),
        skills=(
            replace(profile.skills[0], evidence_ids=()),
            replace(
                profile.skills[1],
                name=" react ",
                evidence_ids=("evi_missing",),
            ),
        ),
    )

    result = _execute(corrupted, _intent())

    assert result.release_eligible is False
    assert _codes(result) == {
        CareerContextReleaseBlockerCode.PROFILE_EVIDENCE_INVALID,
        CareerContextReleaseBlockerCode.PROFILE_EVIDENCE_KEYS_DUPLICATED,
        CareerContextReleaseBlockerCode.PROFILE_SKILL_NAMES_DUPLICATED,
        CareerContextReleaseBlockerCode.PROFILE_SKILL_EVIDENCE_MISSING,
        CareerContextReleaseBlockerCode.PROFILE_SKILL_EVIDENCE_REFERENCE_INVALID,
    }


def test_corrupted_search_intent_fails_closed() -> None:
    intent = replace(
        _intent(),
        target_roles=("Agent Engineer", " agent engineer "),
        minimum_salary_k=-1,
    )

    result = _execute(_profile(), intent)

    assert result.release_eligible is False
    assert _codes(result) == {
        CareerContextReleaseBlockerCode.SEARCH_INTENT_TARGET_ROLES_DUPLICATED,
        CareerContextReleaseBlockerCode.SEARCH_INTENT_MINIMUM_SALARY_INVALID,
    }


def test_blank_target_roles_are_not_released() -> None:
    result = _execute(_profile(), replace(_intent(), target_roles=("  ",)))

    assert result.release_eligible is False
    assert _codes(result) == {
        CareerContextReleaseBlockerCode.SEARCH_INTENT_TARGET_ROLES_MISSING
    }

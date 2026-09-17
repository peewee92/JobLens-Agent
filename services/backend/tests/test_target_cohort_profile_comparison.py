"""Deterministic comparison of normalized TargetCohort capabilities to Profile facts."""
from __future__ import annotations

from datetime import UTC, datetime

from app.application.career_context.models import EvidenceDetail, ProfileDetail, SkillDetail
from app.application.target_cohort_capability_normalization import (
    TargetCohortCapability,
    TargetCohortCapabilityNormalizationResult,
)
from app.application.target_cohort_profile_comparison import (
    CompareTargetCohortCapabilitiesToProfileUseCase,
    ProfileCapabilityCoverageStatus,
)
from app.domain.career_context import EvidenceType, SkillLevel


def _normalization(*capabilities: TargetCohortCapability) -> TargetCohortCapabilityNormalizationResult:
    return TargetCohortCapabilityNormalizationResult(
        cohort_id="cohort_1",
        job_ids=("job_1", "job_2"),
        facts_usable=True,
        capabilities=capabilities,
        blockers=(),
    )


def _capability(
    name: str,
    *,
    requirement_ids: tuple[str, ...],
    job_ids: tuple[str, ...],
    member_options: tuple[str, ...] = (),
) -> TargetCohortCapability:
    return TargetCohortCapability(
        capability=name,
        source_capabilities=(name,),
        requirement_ids=requirement_ids,
        job_ids=job_ids,
        requirement_count=len(requirement_ids),
        job_count=len(job_ids),
        must_have_count=1,
        preferred_count=max(0, len(requirement_ids) - 1),
        bonus_count=0,
        member_options=member_options,
    )


def _profile() -> ProfileDetail:
    return ProfileDetail(
        id="profile_1",
        version=3,
        headline="Frontend engineer",
        years_of_experience=8,
        evidence=(
            EvidenceDetail(
                id="evidence_react",
                key="react-project",
                type=EvidenceType.PROJECT,
                summary="Built production React applications.",
                source="confirmed profile",
            ),
            EvidenceDetail(
                id="evidence_ts",
                key="typescript-project",
                type=EvidenceType.PROJECT,
                summary="Used TypeScript in production.",
                source="confirmed profile",
            ),
        ),
        skills=(
            SkillDetail(
                id="skill_react",
                name="ReactJS",
                level=SkillLevel.STRONG,
                evidence_ids=("evidence_react",),
            ),
            SkillDetail(
                id="skill_ts",
                name="TypeScript",
                level=SkillLevel.STRONG,
                evidence_ids=("evidence_ts",),
            ),
        ),
        created_at=datetime(2026, 8, 10, tzinfo=UTC),
    )


def test_comparison_matches_explicit_alias_and_preserves_both_sides_provenance() -> None:
    result = CompareTargetCohortCapabilitiesToProfileUseCase().execute(
        _normalization(
            _capability("React", requirement_ids=("req_1", "req_2"), job_ids=("job_1", "job_2")),
            _capability("Kafka", requirement_ids=("req_3",), job_ids=("job_2",)),
        ),
        _profile(),
    )

    assert result.facts_usable is True
    assert result.profile_id == "profile_1"
    assert result.profile_version == 3
    assert [item.capability for item in result.capabilities] == ["React", "Kafka"]

    react, kafka = result.capabilities
    assert react.status is ProfileCapabilityCoverageStatus.EVIDENCED
    assert react.requirement_ids == ("req_1", "req_2")
    assert react.job_ids == ("job_1", "job_2")
    assert react.profile_skill_ids == ("skill_react",)
    assert react.evidence_ids == ("evidence_react",)

    assert kafka.status is ProfileCapabilityCoverageStatus.MISSING
    assert kafka.profile_skill_ids == ()
    assert kafka.evidence_ids == ()


def test_explicit_compound_member_option_reuses_exact_confirmed_profile_skill() -> None:
    result = CompareTargetCohortCapabilitiesToProfileUseCase().execute(
        _normalization(
            _capability(
                "Shell/Python/Java/Go/TypeScript",
                requirement_ids=("req_1",),
                job_ids=("job_1",),
                member_options=("Shell", "Python", "Java", "Go", "TypeScript"),
            ),
            _capability(
                "Python、Java",
                requirement_ids=("req_2",),
                job_ids=("job_2",),
            ),
        ),
        _profile(),
    )

    alternative, conjunctive = result.capabilities
    assert alternative.status is ProfileCapabilityCoverageStatus.EVIDENCED
    assert alternative.profile_skill_ids == ("skill_ts",)
    assert alternative.evidence_ids == ("evidence_ts",)
    assert conjunctive.status is ProfileCapabilityCoverageStatus.MISSING
    assert conjunctive.profile_skill_ids == ()
    assert conjunctive.evidence_ids == ()


def test_profile_skill_without_evidence_is_not_upgraded_to_evidenced() -> None:
    profile = _profile()
    profile = ProfileDetail(
        id=profile.id,
        version=profile.version,
        headline=profile.headline,
        years_of_experience=profile.years_of_experience,
        evidence=profile.evidence,
        skills=(
            SkillDetail(
                id="skill_react",
                name="React",
                level=SkillLevel.STRONG,
                evidence_ids=(),
            ),
        ),
        created_at=profile.created_at,
    )

    result = CompareTargetCohortCapabilitiesToProfileUseCase().execute(
        _normalization(_capability("React", requirement_ids=("req_1",), job_ids=("job_1",))),
        profile,
    )

    assert result.capabilities[0].status is ProfileCapabilityCoverageStatus.UNEVIDENCED
    assert result.capabilities[0].profile_skill_ids == ("skill_react",)
    assert result.capabilities[0].evidence_ids == ()


def test_unusable_market_facts_fail_closed_without_profile_comparison() -> None:
    normalization = TargetCohortCapabilityNormalizationResult(
        cohort_id="cohort_1",
        job_ids=("job_1",),
        facts_usable=False,
        capabilities=(),
        blockers=(),
    )

    result = CompareTargetCohortCapabilitiesToProfileUseCase().execute(normalization, _profile())

    assert result.facts_usable is False
    assert result.capabilities == ()
    assert result.db_writes == 0
    assert result.provider_calls == 0
    assert result.trace_runs_created == 0

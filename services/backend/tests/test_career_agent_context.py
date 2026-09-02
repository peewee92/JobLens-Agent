"""Governed Career Agent context builder tests."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from app.agent.context import CareerAgentContextBlocker, CareerAgentContextBuilder
from app.application.career_context.models import (
    CareerContextSnapshot,
    EvidenceDetail,
    ProfileDetail,
    SearchIntentDetail,
    SkillDetail,
)
from app.application.job_queries.models import JobDetail, JobListQuery, JobPage
from app.domain.career_context import EvidenceType, Seniority, SkillLevel
from app.domain.jobs import RemoteConfidence, RemoteStatus

NOW = datetime(2026, 9, 2, 5, 0, tzinfo=timezone.utc)


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
        return self.profile

    def get_current_search_intent(self) -> SearchIntentDetail | None:
        return self.intent


class FakeJobQueryRepository:
    def __init__(self, jobs: tuple[JobDetail, ...] = ()) -> None:
        self.jobs = {job.id: job for job in jobs}

    def fetch_page(self, query: JobListQuery) -> JobPage:
        raise AssertionError("Agent context must not scan the Job Pool")

    def get_job(self, job_id: str) -> JobDetail | None:
        return self.jobs.get(job_id)


def _profile() -> ProfileDetail:
    evidence = EvidenceDetail(
        id="evi_1",
        key="joblens",
        type=EvidenceType.PROJECT,
        summary="Built an evidence-based job matching product.",
        source="confirmed by user",
    )
    return ProfileDetail(
        id="prof_1",
        version=4,
        headline="Frontend and AI application engineer",
        years_of_experience=8,
        evidence=(evidence,),
        skills=(
            SkillDetail(
                id="skill_1",
                name="React",
                level=SkillLevel.STRONG,
                evidence_ids=(evidence.id,),
            ),
        ),
        created_at=NOW,
    )


def _intent() -> SearchIntentDetail:
    return SearchIntentDetail(
        id="intent_1",
        version=3,
        target_roles=("AI Application Engineer",),
        cities=("武汉",),
        remote_accepted=True,
        minimum_salary_k=20,
        seniority=Seniority.SENIOR,
        employment_types=("full_time",),
        exclude_keywords=(),
        hard_constraints=(),
        soft_preferences=("Agent product",),
        created_at=NOW,
    )


def _job() -> JobDetail:
    return JobDetail(
        id="job_1",
        title="AI Application Engineer",
        company="Example AI",
        area="武汉",
        salary_min_k=20,
        salary_max_k=35,
        experience="5-10 years",
        education="Bachelor",
        description="Raw JD content that must not enter Agent context.",
        skills=("React", "Python"),
        remote_status=RemoteStatus.UNKNOWN,
        remote_confidence=RemoteConfidence.LOW,
        source="collector",
        source_url="https://example.invalid/job/1",
        source_version="v1",
        description_quality="complete",
        requirement_review_eligible=True,
        requirement_review_ineligibility_reasons=(),
        collected_at=NOW,
    )


def test_builds_context_only_from_released_profile_intent_and_safe_job_metadata() -> None:
    profile = _profile()
    intent = _intent()
    builder = CareerAgentContextBuilder(
        career_context=FakeCareerContextQueryRepository(
            profile=profile,
            intent=intent,
        ),
        jobs=FakeJobQueryRepository((_job(),)),
    )

    result = builder.build(
        current_job_id="job_1",
        relevant_evidence_ids=("evi_1", "evi_1"),
    )

    assert result.usable is True
    assert result.profile is not None
    assert result.profile.id == profile.id
    assert result.profile.version == profile.version
    assert result.profile.headline == profile.headline
    assert not hasattr(result.profile, "evidence")
    assert result.search_intent == intent
    assert result.current_job is not None
    assert result.current_job.id == "job_1"
    assert result.current_job.title == "AI Application Engineer"
    assert not hasattr(result.current_job, "description")
    assert [item.id for item in result.relevant_evidence] == ["evi_1"]
    assert result.relevant_evidence[0].summary == profile.evidence[0].summary
    assert result.blockers == ()
    assert (result.db_writes, result.provider_calls, result.trace_runs_created) == (0, 0, 0)


def test_unreleased_career_context_fails_closed_and_withholds_partial_facts() -> None:
    builder = CareerAgentContextBuilder(
        career_context=FakeCareerContextQueryRepository(
            profile=_profile(),
            intent=None,
        ),
        jobs=FakeJobQueryRepository(),
    )

    result = builder.build()

    assert result.usable is False
    assert result.profile is None
    assert result.search_intent is None
    assert result.current_job is None
    assert result.blockers == (
        CareerAgentContextBlocker.CAREER_CONTEXT_NOT_RELEASED,
    )
    assert any("SearchIntent" in message for message in result.blocker_messages)


def test_missing_explicit_current_job_fails_closed_without_scanning_or_guessing() -> None:
    builder = CareerAgentContextBuilder(
        career_context=FakeCareerContextQueryRepository(
            profile=_profile(),
            intent=_intent(),
        ),
        jobs=FakeJobQueryRepository(),
    )

    result = builder.build(current_job_id="job_missing")

    assert result.usable is False
    assert result.current_job is None
    assert result.profile is None
    assert result.search_intent is None
    assert CareerAgentContextBlocker.CURRENT_JOB_NOT_FOUND in result.blockers


def test_unconfirmed_requested_evidence_fails_closed_instead_of_guessing() -> None:
    builder = CareerAgentContextBuilder(
        career_context=FakeCareerContextQueryRepository(
            profile=_profile(),
            intent=_intent(),
        ),
        jobs=FakeJobQueryRepository(),
    )

    result = builder.build(relevant_evidence_ids=("evi_missing",))

    assert result.usable is False
    assert result.profile is None
    assert result.relevant_evidence == ()
    assert result.blockers == (
        CareerAgentContextBlocker.RELEVANT_EVIDENCE_NOT_CONFIRMED,
    )


def test_context_fails_closed_when_confirmed_identity_changes_between_release_and_read() -> None:
    repo = FakeCareerContextQueryRepository(profile=_profile(), intent=_intent())
    original_get = repo.get_current_context
    calls = 0

    def drifting_get_current_context() -> CareerContextSnapshot:
        nonlocal calls
        calls += 1
        snapshot = original_get()
        if calls == 1:
            return snapshot
        assert snapshot.profile is not None
        return replace(snapshot, profile=replace(snapshot.profile, version=5))

    repo.get_current_context = drifting_get_current_context  # type: ignore[method-assign]
    builder = CareerAgentContextBuilder(
        career_context=repo,
        jobs=FakeJobQueryRepository(),
    )

    result = builder.build()

    assert result.usable is False
    assert result.profile is None
    assert result.search_intent is None
    assert result.blockers == (
        CareerAgentContextBlocker.CAREER_CONTEXT_IDENTITY_CHANGED,
    )

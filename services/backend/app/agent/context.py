"""Governed context for the single Career Agent orchestration layer.

The builder deliberately exposes only explicitly confirmed career facts and
safe current-job metadata. P0 context excludes Evidence bodies; P1 Evidence
must be explicitly selected by immutable confirmed Evidence IDs. The builder
does not expose raw JD text, run an LLM, call a Provider, create a Trace, or
duplicate Match/Gap/Prepare business rules.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.application.career_context.models import (
    CareerContextSnapshot,
    ProfileDetail,
    SearchIntentDetail,
)
from app.application.career_context.release import (
    CareerContextReleaseReadiness,
    GetCareerContextReleaseReadinessUseCase,
)
from app.application.ports.career_context_repository import (
    AbstractCareerContextQueryRepository,
)
from app.application.ports.job_query_repository import AbstractJobQueryRepository
from app.domain.career_context import EvidenceType, SkillLevel


class CareerAgentContextBlocker(StrEnum):
    CAREER_CONTEXT_NOT_RELEASED = "career_context_not_released"
    CAREER_CONTEXT_IDENTITY_CHANGED = "career_context_identity_changed"
    CURRENT_JOB_NOT_FOUND = "current_job_not_found"
    RELEVANT_EVIDENCE_NOT_CONFIRMED = "relevant_evidence_not_confirmed"


@dataclass(frozen=True, slots=True)
class CareerAgentSkillContext:
    id: str
    name: str
    level: SkillLevel


@dataclass(frozen=True, slots=True)
class CareerAgentProfileContext:
    """P0 Profile facts without Evidence bodies."""

    id: str
    version: int
    headline: str
    years_of_experience: float | None
    skills: tuple[CareerAgentSkillContext, ...]


@dataclass(frozen=True, slots=True)
class CareerAgentEvidenceContext:
    """P1 Evidence explicitly selected from the current confirmed Profile."""

    id: str
    type: EvidenceType
    summary: str
    source: str


@dataclass(frozen=True, slots=True)
class CareerAgentJobContext:
    """Safe current-job identity/metadata available to orchestration.

    Raw JD text is intentionally excluded. Match/Gap/Prepare must continue to
    consume released JobRequirement facts through their existing workflows.
    """

    id: str
    title: str
    company: str
    area: str | None


@dataclass(frozen=True, slots=True)
class CareerAgentContext:
    usable: bool
    confirmation_boundary: str
    profile: CareerAgentProfileContext | None
    search_intent: SearchIntentDetail | None
    current_job: CareerAgentJobContext | None
    relevant_evidence: tuple[CareerAgentEvidenceContext, ...]
    blockers: tuple[CareerAgentContextBlocker, ...]
    blocker_messages: tuple[str, ...]
    db_writes: int = 0
    provider_calls: int = 0
    trace_runs_created: int = 0


class CareerAgentContextBuilder:
    """Build the minimum governed context an Agent may use for orchestration."""

    def __init__(
        self,
        *,
        career_context: AbstractCareerContextQueryRepository,
        jobs: AbstractJobQueryRepository,
        release_readiness: GetCareerContextReleaseReadinessUseCase | None = None,
    ) -> None:
        self._career_context = career_context
        self._jobs = jobs
        self._release_readiness = release_readiness or (
            GetCareerContextReleaseReadinessUseCase(career_context)
        )

    def build(
        self,
        *,
        current_job_id: str | None = None,
        relevant_evidence_ids: tuple[str, ...] = (),
    ) -> CareerAgentContext:
        readiness = self._release_readiness.execute()
        snapshot = self._career_context.get_current_context()
        blockers: list[CareerAgentContextBlocker] = []
        messages: list[str] = []

        if not readiness.release_eligible:
            blockers.append(CareerAgentContextBlocker.CAREER_CONTEXT_NOT_RELEASED)
            messages.extend(blocker.message for blocker in readiness.blockers)
        elif not self._same_released_identity(readiness, snapshot):
            blockers.append(CareerAgentContextBlocker.CAREER_CONTEXT_IDENTITY_CHANGED)
            messages.append(
                "Confirmed Profile/SearchIntent changed while Agent context was being built."
            )

        current_job: CareerAgentJobContext | None = None
        if current_job_id is not None:
            job = self._jobs.get_job(current_job_id)
            if job is None:
                blockers.append(CareerAgentContextBlocker.CURRENT_JOB_NOT_FOUND)
                messages.append(f"Current Job does not exist: {current_job_id}")
            else:
                current_job = CareerAgentJobContext(
                    id=job.id,
                    title=job.title,
                    company=job.company,
                    area=job.area,
                )

        relevant_evidence: tuple[CareerAgentEvidenceContext, ...] = ()
        if readiness.release_eligible and snapshot.profile is not None:
            relevant_evidence, missing_evidence_ids = self._select_relevant_evidence(
                snapshot.profile,
                relevant_evidence_ids,
            )
            if missing_evidence_ids:
                blockers.append(
                    CareerAgentContextBlocker.RELEVANT_EVIDENCE_NOT_CONFIRMED
                )
                messages.append(
                    "Requested Agent Evidence is not present in the current confirmed Profile: "
                    + ", ".join(missing_evidence_ids)
                )

        if blockers:
            return CareerAgentContext(
                usable=False,
                confirmation_boundary=readiness.confirmation_boundary,
                profile=None,
                search_intent=None,
                current_job=None,
                relevant_evidence=(),
                blockers=tuple(blockers),
                blocker_messages=tuple(messages),
            )

        assert snapshot.profile is not None
        assert snapshot.search_intent is not None
        return CareerAgentContext(
            usable=True,
            confirmation_boundary=readiness.confirmation_boundary,
            profile=self._profile_context(snapshot.profile),
            search_intent=snapshot.search_intent,
            current_job=current_job,
            relevant_evidence=relevant_evidence,
            blockers=(),
            blocker_messages=(),
        )

    @staticmethod
    def _profile_context(profile: ProfileDetail) -> CareerAgentProfileContext:
        return CareerAgentProfileContext(
            id=profile.id,
            version=profile.version,
            headline=profile.headline,
            years_of_experience=profile.years_of_experience,
            skills=tuple(
                CareerAgentSkillContext(id=skill.id, name=skill.name, level=skill.level)
                for skill in profile.skills
            ),
        )

    @staticmethod
    def _select_relevant_evidence(
        profile: ProfileDetail,
        evidence_ids: tuple[str, ...],
    ) -> tuple[tuple[CareerAgentEvidenceContext, ...], tuple[str, ...]]:
        by_id = {item.id: item for item in profile.evidence}
        selected: list[CareerAgentEvidenceContext] = []
        missing: list[str] = []
        seen: set[str] = set()
        for evidence_id in evidence_ids:
            if evidence_id in seen:
                continue
            seen.add(evidence_id)
            item = by_id.get(evidence_id)
            if item is None:
                missing.append(evidence_id)
                continue
            selected.append(
                CareerAgentEvidenceContext(
                    id=item.id,
                    type=item.type,
                    summary=item.summary,
                    source=item.source,
                )
            )
        return tuple(selected), tuple(missing)

    @staticmethod
    def _same_released_identity(
        readiness: CareerContextReleaseReadiness,
        snapshot: CareerContextSnapshot,
    ) -> bool:
        profile = snapshot.profile
        intent = snapshot.search_intent
        return (
            profile is not None
            and intent is not None
            and readiness.profile_id == profile.id
            and readiness.profile_version == profile.version
            and readiness.search_intent_id == intent.id
            and readiness.search_intent_version == intent.version
        )

"""Read-only preflight that composes the two trusted Match input gates."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from app.application.career_context.release import CareerContextReleaseReadiness
from app.application.job_requirements.release import JobRequirementReleaseReadiness


class CareerContextGate(Protocol):
    def execute(self) -> CareerContextReleaseReadiness: ...


class JobRequirementGate(Protocol):
    def execute(self, job_id: str) -> JobRequirementReleaseReadiness: ...


class MatchInputBlockerSource(StrEnum):
    CAREER_CONTEXT = "career_context"
    JOB_REQUIREMENTS = "job_requirements"


@dataclass(frozen=True, slots=True)
class MatchInputBlocker:
    source: MatchInputBlockerSource
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class MatchInputReadiness:
    job_id: str
    inputs_release_eligible: bool
    career_context: CareerContextReleaseReadiness
    job_requirements: JobRequirementReleaseReadiness
    blockers: tuple[MatchInputBlocker, ...]
    db_writes: int = 0
    provider_calls: int = 0
    trace_runs_created: int = 0


class GetMatchInputReadinessUseCase:
    """Combine trusted facts without running Eligibility, Match, or Provider work."""

    def __init__(
        self,
        *,
        career_context: CareerContextGate,
        job_requirements: JobRequirementGate,
    ) -> None:
        self._career_context = career_context
        self._job_requirements = job_requirements

    def execute(self, job_id: str) -> MatchInputReadiness:
        career = self._career_context.execute()
        requirements = self._job_requirements.execute(job_id)
        blockers = tuple(
            MatchInputBlocker(
                source=MatchInputBlockerSource.CAREER_CONTEXT,
                code=item.code.value,
                message=item.message,
            )
            for item in career.blockers
        ) + tuple(
            MatchInputBlocker(
                source=MatchInputBlockerSource.JOB_REQUIREMENTS,
                code=item.code.value,
                message=item.message,
            )
            for item in requirements.blockers
        )
        return MatchInputReadiness(
            job_id=job_id,
            inputs_release_eligible=(
                career.release_eligible and requirements.release_eligible
            ),
            career_context=career,
            job_requirements=requirements,
            blockers=blockers,
        )

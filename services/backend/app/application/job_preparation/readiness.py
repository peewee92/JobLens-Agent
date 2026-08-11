"""Read-only readiness gate for Phase 7 Job Preparation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.application.match_inputs.readiness import MatchInputBlocker, MatchInputReadiness


class MatchInputGate(Protocol):
    def execute(self, job_id: str) -> MatchInputReadiness: ...


@dataclass(frozen=True, slots=True)
class JobPreparationReadiness:
    job_id: str
    preparation_inputs_ready: bool
    profile_id: str | None
    profile_version: int | None
    extraction_id: str | None
    requirement_count: int
    blockers: tuple[MatchInputBlocker, ...]
    db_writes: int = 0
    provider_calls: int = 0
    trace_runs_created: int = 0


class GetJobPreparationReadinessUseCase:
    """Freeze trusted Profile and Requirement identities before preparation work."""

    def __init__(self, *, match_inputs: MatchInputGate) -> None:
        self._match_inputs = match_inputs

    def execute(self, job_id: str) -> JobPreparationReadiness:
        match_inputs = self._match_inputs.execute(job_id)
        ready = match_inputs.inputs_release_eligible
        return JobPreparationReadiness(
            job_id=job_id,
            preparation_inputs_ready=ready,
            profile_id=match_inputs.career_context.profile_id if ready else None,
            profile_version=match_inputs.career_context.profile_version if ready else None,
            extraction_id=match_inputs.job_requirements.extraction_id if ready else None,
            requirement_count=match_inputs.job_requirements.requirement_count if ready else 0,
            blockers=match_inputs.blockers,
        )

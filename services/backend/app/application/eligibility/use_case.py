"""Read-only Eligibility orchestration guarded by trusted Match inputs."""
from __future__ import annotations

from typing import Protocol

from app.application.career_context.models import ProfileDetail
from app.application.eligibility.errors import EligibilityInputsNotReadyError
from app.application.eligibility.evaluator import evaluate_eligibility
from app.application.eligibility.models import JobEligibilityResult
from app.application.job_requirements.models import JobRequirementExtractionDetail
from app.application.ports.career_context_repository import AbstractCareerContextQueryRepository
from app.application.ports.job_requirement_repository import AbstractJobRequirementQueryRepository
from app.application.match_inputs.readiness import MatchInputReadiness


class MatchInputReadinessGate(Protocol):
    def execute(self, job_id: str) -> MatchInputReadiness: ...


class EvaluateJobEligibilityUseCase:
    """Evaluate deterministic eligibility without Provider, Trace, or DB writes."""

    def __init__(
        self,
        *,
        readiness: MatchInputReadinessGate,
        profiles: AbstractCareerContextQueryRepository,
        requirements: AbstractJobRequirementQueryRepository,
    ) -> None:
        self._readiness = readiness
        self._profiles = profiles
        self._requirements = requirements

    def execute(self, job_id: str) -> JobEligibilityResult:
        readiness = self._readiness.execute(job_id)
        if not readiness.inputs_release_eligible:
            raise EligibilityInputsNotReadyError(
                "Eligibility requires current confirmed Profile/SearchIntent and a human-accepted current Requirement fact set."
            )

        profile = self._profiles.get_current_profile()
        extraction = self._requirements.get_latest(job_id)
        if profile is None or extraction is None:
            raise EligibilityInputsNotReadyError(
                "Eligibility inputs disappeared after readiness evaluation."
            )
        return evaluate_eligibility(profile=profile, extraction=extraction)

"""Read-only Eligibility orchestration guarded by trusted Match inputs."""
from __future__ import annotations

from typing import Protocol
from dataclasses import replace

from app.application.search_preferences import (
    evaluate_search_preferences, preference_input_fingerprint, PreferenceFitStatus,
)
from app.application.eligibility.models import EligibilityDecision
from app.application.ports.job_query_repository import AbstractJobQueryRepository

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
        jobs: AbstractJobQueryRepository,
    ) -> None:
        self._readiness = readiness
        self._profiles = profiles
        self._requirements = requirements
        self._jobs = jobs

    def execute(self, job_id: str) -> JobEligibilityResult:
        readiness = self._readiness.execute(job_id)
        if not readiness.inputs_release_eligible:
            raise EligibilityInputsNotReadyError(
                "Eligibility requires current confirmed Profile/SearchIntent and a human-accepted current Requirement fact set."
            )

        profile = self._profiles.get_current_profile()
        extraction = self._requirements.get_latest(job_id)
        intent = self._profiles.get_current_search_intent()
        job = self._jobs.get_job(job_id)
        if profile is None or extraction is None or intent is None or job is None:
            raise EligibilityInputsNotReadyError(
                "Eligibility inputs disappeared after readiness evaluation."
            )
        if (
            intent.id != readiness.career_context.search_intent_id
            or intent.version != readiness.career_context.search_intent_version
            or job.id != job_id
            or profile.id != readiness.career_context.profile_id
            or profile.version != readiness.career_context.profile_version
            or extraction.extraction_id != readiness.job_requirements.extraction_id
            or extraction.job_id != job_id
        ):
            raise EligibilityInputsNotReadyError(
                "Eligibility inputs changed after readiness evaluation."
            )
        return evaluate_match_eligibility(profile=profile, extraction=extraction, intent=intent, job=job)


def evaluate_match_eligibility(*, profile, extraction, intent, job):
    """The shared deterministic rules on an already-captured fact set."""
    result = evaluate_eligibility(profile=profile, extraction=extraction)
    checks = evaluate_search_preferences(intent, job)
    decision = result.eligibility
    if any(item.status is PreferenceFitStatus.MISSING for item in checks):
        decision = EligibilityDecision.BLOCKED
    elif decision is not EligibilityDecision.BLOCKED and any(
        item.status is PreferenceFitStatus.CONDITIONAL for item in checks
    ):
        decision = EligibilityDecision.CONDITIONAL
    return replace(result, eligibility=decision, search_intent_id=intent.id,
                   search_intent_version=intent.version, preference_checks=checks,
                   preference_fingerprint=preference_input_fingerprint(intent, job))

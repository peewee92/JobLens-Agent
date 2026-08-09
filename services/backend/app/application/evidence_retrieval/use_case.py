"""Read-only Evidence Retrieval orchestration guarded by trusted Match inputs."""
from __future__ import annotations

from typing import Protocol

from app.application.evidence_retrieval.errors import EvidenceRetrievalInputsNotReadyError
from app.application.evidence_retrieval.models import JobEvidenceRetrievalResult
from app.application.evidence_retrieval.retriever import retrieve_candidate_evidence
from app.application.match_inputs.readiness import MatchInputReadiness
from app.application.ports.career_context_repository import AbstractCareerContextQueryRepository
from app.application.ports.job_requirement_repository import AbstractJobRequirementQueryRepository


class MatchInputReadinessGate(Protocol):
    def execute(self, job_id: str) -> MatchInputReadiness: ...


class RetrieveJobEvidenceUseCase:
    """Retrieve candidate Evidence without Provider, Trace, verdicts, or DB writes."""

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

    def execute(self, job_id: str) -> JobEvidenceRetrievalResult:
        readiness = self._readiness.execute(job_id)
        if not readiness.inputs_release_eligible:
            raise EvidenceRetrievalInputsNotReadyError(
                "Evidence Retrieval requires current confirmed Profile/SearchIntent and a human-accepted current Requirement fact set."
            )

        profile = self._profiles.get_current_profile()
        extraction = self._requirements.get_latest(job_id)
        if profile is None or extraction is None:
            raise EvidenceRetrievalInputsNotReadyError(
                "Evidence Retrieval inputs disappeared after readiness evaluation."
            )
        if (
            profile.id != readiness.career_context.profile_id
            or profile.version != readiness.career_context.profile_version
            or extraction.extraction_id != readiness.job_requirements.extraction_id
            or extraction.job_id != job_id
        ):
            raise EvidenceRetrievalInputsNotReadyError(
                "Evidence Retrieval inputs changed after readiness evaluation."
            )
        return retrieve_candidate_evidence(profile=profile, extraction=extraction)

"""Application orchestration for one transient Semantic Match run."""
from __future__ import annotations

from app.application.job_availability_guard import matching_availability_revision
from app.application.ports.job_query_repository import AbstractJobQueryRepository
from app.application.eligibility import (
    EligibilityInputsNotReadyError,
    EvaluateJobEligibilityUseCase,
)
from app.application.evidence_retrieval import (
    EvidenceRetrievalInputsNotReadyError,
    RetrieveJobEvidenceUseCase,
)
from app.application.semantic_match.errors import SemanticMatchInputsNotReadyError
from app.application.semantic_match.models import JobSemanticMatchResult
from app.workflows.semantic_match import SemanticMatchWorkflow


class RunJobSemanticMatchUseCase:
    """Compose trusted Eligibility + Retrieval inputs into a Semantic Match run."""

    def __init__(
        self,
        *,
        eligibility: EvaluateJobEligibilityUseCase,
        evidence: RetrieveJobEvidenceUseCase,
        workflow: SemanticMatchWorkflow,
        jobs: AbstractJobQueryRepository | None = None,
    ) -> None:
        self._jobs = jobs
        self._eligibility = eligibility
        self._evidence = evidence
        self._workflow = workflow

    def execute(self, job_id: str) -> JobSemanticMatchResult:
        if self._jobs is not None:
            matching_availability_revision(self._jobs, job_id)
        try:
            eligibility = self._eligibility.execute(job_id)
            evidence = self._evidence.execute(job_id)
        except (
            EligibilityInputsNotReadyError,
            EvidenceRetrievalInputsNotReadyError,
        ) as error:
            raise SemanticMatchInputsNotReadyError(
                "Semantic Match requires current released Eligibility and Evidence Retrieval inputs."
            ) from error
        return self._workflow.execute(
            eligibility=eligibility,
            evidence=evidence,
        )

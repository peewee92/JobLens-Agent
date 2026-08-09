"""Application orchestration for one transient Semantic Match run."""
from __future__ import annotations

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
    ) -> None:
        self._eligibility = eligibility
        self._evidence = evidence
        self._workflow = workflow

    def execute(self, job_id: str) -> JobSemanticMatchResult:
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

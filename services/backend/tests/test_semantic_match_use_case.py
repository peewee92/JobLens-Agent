"""Semantic Match application boundary keeps one stable readiness error contract."""
from __future__ import annotations

import pytest

from app.application.eligibility import EligibilityInputsNotReadyError
from app.application.evidence_retrieval import EvidenceRetrievalInputsNotReadyError
from app.application.semantic_match import SemanticMatchInputsNotReadyError
from app.application.semantic_match.use_case import RunJobSemanticMatchUseCase


class _EligibilityNotReady:
    def execute(self, _job_id: str):
        raise EligibilityInputsNotReadyError("eligibility gate not ready")


class _EligibilityReady:
    def execute(self, _job_id: str):
        return object()


class _EvidenceNotReady:
    def execute(self, _job_id: str):
        raise EvidenceRetrievalInputsNotReadyError("evidence gate not ready")


class _UnusedEvidence:
    def execute(self, _job_id: str):
        raise AssertionError("evidence should not run after eligibility failure")


class _UnusedWorkflow:
    def execute(self, **_kwargs):
        raise AssertionError("workflow should not run when trusted inputs are not ready")


def test_eligibility_readiness_failure_is_translated_to_semantic_match_boundary() -> None:
    use_case = RunJobSemanticMatchUseCase(
        eligibility=_EligibilityNotReady(),
        evidence=_UnusedEvidence(),
        workflow=_UnusedWorkflow(),
    )

    with pytest.raises(SemanticMatchInputsNotReadyError):
        use_case.execute("job_1")


def test_evidence_readiness_failure_is_translated_to_semantic_match_boundary() -> None:
    use_case = RunJobSemanticMatchUseCase(
        eligibility=_EligibilityReady(),
        evidence=_EvidenceNotReady(),
        workflow=_UnusedWorkflow(),
    )

    with pytest.raises(SemanticMatchInputsNotReadyError):
        use_case.execute("job_1")

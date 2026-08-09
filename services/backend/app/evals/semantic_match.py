"""Synthetic Semantic Match contract evaluation without an automatic quality gate."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from app.application.eligibility.models import (
    EligibilityDecision,
    JobEligibilityResult,
    RequirementEligibilityResult,
    RequirementFitStatus,
)
from app.application.evidence_retrieval.models import (
    CandidateEvidence,
    EvidenceRelevanceTier,
    EvidenceRetrievalBasis,
    JobEvidenceRetrievalResult,
    RequirementEvidenceCandidates,
)
from app.domain.career_context import EvidenceType
from app.domain.job_requirements import RequirementImportance, RequirementType
from app.workflows.semantic_match import SemanticMatchWorkflow


@dataclass(frozen=True, slots=True)
class SemanticMatchEvalCase:
    id: str
    eligibility: JobEligibilityResult
    evidence: JobEvidenceRetrievalResult
    expected_eligibility: str
    expected_verdict: str


@dataclass(frozen=True, slots=True)
class SemanticMatchEvalCaseResult:
    case_id: str
    passed: bool
    expected_eligibility: str
    actual_eligibility: str | None
    expected_verdict: str
    actual_verdict: str | None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class SemanticMatchEvalReport:
    total: int
    passed: int
    failed: int
    cases: tuple[SemanticMatchEvalCaseResult, ...]


def load_semantic_match_eval_cases(path: Path) -> tuple[SemanticMatchEvalCase, ...]:
    cases: list[SemanticMatchEvalCase] = []
    seen_ids: set[str] = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        payload = json.loads(line)
        case_id = str(payload["id"])
        if case_id in seen_ids:
            raise ValueError(
                f"Duplicate Semantic Match Eval case id {case_id!r} at line {line_number}"
            )
        seen_ids.add(case_id)
        cases.append(_case_from_payload(case_id, payload))
    if not cases:
        raise ValueError(f"No Semantic Match Eval cases found in {path}")
    return tuple(cases)


def run_semantic_match_eval(
    *,
    cases: tuple[SemanticMatchEvalCase, ...],
    workflow: SemanticMatchWorkflow,
) -> SemanticMatchEvalReport:
    results: list[SemanticMatchEvalCaseResult] = []
    for case in cases:
        try:
            result = workflow.execute(
                eligibility=case.eligibility,
                evidence=case.evidence,
            )
            actual_verdict = result.assessments[0].verdict.value
            actual_eligibility = result.eligibility.value
            passed = (
                actual_verdict == case.expected_verdict
                and actual_eligibility == case.expected_eligibility
            )
            results.append(
                SemanticMatchEvalCaseResult(
                    case_id=case.id,
                    passed=passed,
                    expected_eligibility=case.expected_eligibility,
                    actual_eligibility=actual_eligibility,
                    expected_verdict=case.expected_verdict,
                    actual_verdict=actual_verdict,
                )
            )
        except Exception as error:
            results.append(
                SemanticMatchEvalCaseResult(
                    case_id=case.id,
                    passed=False,
                    expected_eligibility=case.expected_eligibility,
                    actual_eligibility=None,
                    expected_verdict=case.expected_verdict,
                    actual_verdict=None,
                    error=f"{type(error).__name__}: {error}",
                )
            )

    result_tuple = tuple(results)
    passed = sum(item.passed for item in result_tuple)
    return SemanticMatchEvalReport(
        total=len(result_tuple),
        passed=passed,
        failed=len(result_tuple) - passed,
        cases=result_tuple,
    )


def _case_from_payload(case_id: str, payload: dict) -> SemanticMatchEvalCase:
    requirement = payload["requirement"]
    job_id = f"job_{case_id}"
    profile_id = f"profile_{case_id}"
    extraction_id = f"reqrun_{case_id}"
    requirement_id = str(requirement["id"])
    requirement_type = RequirementType(str(requirement["type"]))
    importance = RequirementImportance(str(requirement["importance"]))
    eligibility_status = RequirementFitStatus(str(requirement["eligibilityStatus"]))
    original_text = str(requirement["originalText"])
    normalized_capability = (
        str(requirement["normalizedCapability"])
        if requirement.get("normalizedCapability") is not None
        else None
    )
    eligibility = JobEligibilityResult(
        job_id=job_id,
        profile_id=profile_id,
        profile_version=1,
        extraction_id=extraction_id,
        eligibility=EligibilityDecision(str(payload["eligibility"])),
        requirements=(
            RequirementEligibilityResult(
                requirement_id=requirement_id,
                requirement_index=0,
                type=requirement_type,
                importance=importance,
                original_text=original_text,
                normalized_capability=normalized_capability,
                status=eligibility_status,
                evidence_ids=tuple(
                    str(item) for item in requirement.get("eligibilityEvidenceIds", [])
                ),
                profile_fact_refs=tuple(
                    str(item) for item in requirement.get("profileFactRefs", [])
                ),
                reason="Synthetic eval Eligibility fixture.",
            ),
        ),
        matched_count=int(eligibility_status is RequirementFitStatus.MATCHED),
        conditional_count=int(eligibility_status is RequirementFitStatus.CONDITIONAL),
        missing_count=int(eligibility_status is RequirementFitStatus.MISSING),
    )
    candidates = tuple(
        CandidateEvidence(
            evidence_id=str(item["evidenceId"]),
            evidence_key=str(item["evidenceKey"]),
            evidence_type=EvidenceType(str(item["evidenceType"])),
            summary=str(item["summary"]),
            source=str(item["source"]),
            relevance_tier=EvidenceRelevanceTier(str(item["relevanceTier"])),
            retrieval_basis=EvidenceRetrievalBasis(str(item["retrievalBasis"])),
            matched_terms=tuple(str(value) for value in item.get("matchedTerms", [])),
            reason="Synthetic eval retrieval fixture.",
        )
        for item in payload.get("candidates", [])
    )
    evidence = JobEvidenceRetrievalResult(
        job_id=job_id,
        profile_id=profile_id,
        profile_version=1,
        extraction_id=extraction_id,
        requirements=(
            RequirementEvidenceCandidates(
                requirement_id=requirement_id,
                requirement_index=0,
                type=requirement_type,
                importance=importance,
                original_text=original_text,
                normalized_capability=normalized_capability,
                candidates=candidates,
            ),
        ),
        candidate_count=len(candidates),
    )
    return SemanticMatchEvalCase(
        id=case_id,
        eligibility=eligibility,
        evidence=evidence,
        expected_eligibility=str(payload["expectedEligibility"]),
        expected_verdict=str(payload["expectedVerdict"]),
    )

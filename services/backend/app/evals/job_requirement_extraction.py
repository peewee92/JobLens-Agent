"""Repeatable Job Requirement Extraction evaluation runner."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from app.application.job_requirements import JobRequirementExtractionExecutionError
from app.domain.job_requirements import RequirementImportance, RequirementType
from app.workflows import ExtractJobRequirementsWorkflow


@dataclass(frozen=True, slots=True)
class ExpectedRequirement:
    type: RequirementType
    normalized_capability: str | None
    importance: RequirementImportance


@dataclass(frozen=True, slots=True)
class JobRequirementEvalCase:
    case_id: str
    job_id: str
    description: str
    expected_requirements: tuple[ExpectedRequirement, ...]
    forbidden_capabilities: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class JobRequirementEvalCaseResult:
    case_id: str
    trace_run_id: str | None
    workflow_succeeded: bool
    passed: bool
    missing_requirements: tuple[str, ...]
    wrong_importance: tuple[str, ...]
    observed_forbidden_capabilities: tuple[str, ...]
    actual_requirements: tuple[str, ...]
    error: str | None


@dataclass(frozen=True, slots=True)
class JobRequirementEvalReport:
    dataset_version: str
    total_cases: int
    passed_cases: int
    case_pass_rate: float
    workflow_success_rate: float
    capability_recall: float
    importance_accuracy: float
    forbidden_capability_rate: float
    gate_passed: bool
    cases: tuple[JobRequirementEvalCaseResult, ...]


CASE_PASS_THRESHOLD = 0.9
WORKFLOW_SUCCESS_THRESHOLD = 1.0
CAPABILITY_RECALL_THRESHOLD = 0.95
IMPORTANCE_ACCURACY_THRESHOLD = 0.9
FORBIDDEN_CAPABILITY_RATE_THRESHOLD = 0.0


def load_job_requirement_eval_cases(path: Path) -> tuple[JobRequirementEvalCase, ...]:
    cases: list[JobRequirementEvalCase] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        payload = json.loads(line)
        try:
            cases.append(
                JobRequirementEvalCase(
                    case_id=str(payload["caseId"]),
                    job_id=str(payload["jobId"]),
                    description=str(payload["description"]),
                    expected_requirements=tuple(
                        ExpectedRequirement(
                            type=RequirementType(item["type"]),
                            normalized_capability=item.get("normalizedCapability"),
                            importance=RequirementImportance(item["importance"]),
                        )
                        for item in payload["expectedRequirements"]
                    ),
                    forbidden_capabilities=tuple(payload.get("forbiddenCapabilities", [])),
                )
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"Invalid Requirement Eval case at line {line_number}") from error
    if len(cases) < 10:
        raise ValueError("Requirement Eval dataset must contain at least 10 cases")
    if len({case.case_id for case in cases}) != len(cases):
        raise ValueError("Requirement Eval caseId values must be unique")
    return tuple(cases)


def run_job_requirement_eval(
    *,
    workflow: ExtractJobRequirementsWorkflow,
    cases: tuple[JobRequirementEvalCase, ...],
    dataset_version: str,
) -> JobRequirementEvalReport:
    results: list[JobRequirementEvalCaseResult] = []
    total_expected_capabilities = 0
    found_expected_capabilities = 0
    total_expected_importance = 0
    correct_expected_importance = 0
    forbidden_case_count = 0
    workflow_successes = 0

    for case in cases:
        try:
            proposal = workflow.execute(job_id=case.job_id, description=case.description)
        except JobRequirementExtractionExecutionError as error:
            results.append(
                JobRequirementEvalCaseResult(
                    case_id=case.case_id,
                    trace_run_id=error.run_id,
                    workflow_succeeded=False,
                    passed=False,
                    missing_requirements=tuple(
                        _expected_label(item) for item in case.expected_requirements
                    ),
                    wrong_importance=(),
                    observed_forbidden_capabilities=(),
                    actual_requirements=(),
                    error=str(error),
                )
            )
            total_expected_capabilities += sum(
                item.normalized_capability is not None
                for item in case.expected_requirements
            )
            total_expected_importance += len(case.expected_requirements)
            continue

        workflow_successes += 1
        actual = proposal.requirements
        actual_labels = tuple(
            f"{item.type.value}:{item.normalized_capability or '-'}:{item.importance.value}"
            for item in actual
        )
        missing: list[str] = []
        wrong_importance: list[str] = []
        for expected in case.expected_requirements:
            capability_matches = [
                item
                for item in actual
                if item.type is expected.type
                and _capability_equal(
                    item.normalized_capability,
                    expected.normalized_capability,
                )
            ]
            if expected.normalized_capability is not None:
                total_expected_capabilities += 1
                if capability_matches:
                    found_expected_capabilities += 1
            total_expected_importance += 1
            if not capability_matches:
                missing.append(_expected_label(expected))
                continue
            if any(item.importance is expected.importance for item in capability_matches):
                correct_expected_importance += 1
            else:
                wrong_importance.append(_expected_label(expected))

        actual_capabilities = {
            item.normalized_capability.casefold()
            for item in actual
            if item.normalized_capability
        }
        observed_forbidden = tuple(
            capability
            for capability in case.forbidden_capabilities
            if capability.casefold() in actual_capabilities
        )
        if observed_forbidden:
            forbidden_case_count += 1
        grounded = all(
            item.evidence_span in case.description
            and item.original_text in case.description
            for item in actual
        )
        passed = not missing and not wrong_importance and not observed_forbidden and grounded
        results.append(
            JobRequirementEvalCaseResult(
                case_id=case.case_id,
                trace_run_id=proposal.trace_run_id,
                workflow_succeeded=True,
                passed=passed,
                missing_requirements=tuple(missing),
                wrong_importance=tuple(wrong_importance),
                observed_forbidden_capabilities=observed_forbidden,
                actual_requirements=actual_labels,
                error=None if grounded else "Requirement evidence was not grounded",
            )
        )

    total = len(cases)
    passed_cases = sum(item.passed for item in results)
    case_rate = passed_cases / total if total else 0.0
    workflow_rate = workflow_successes / total if total else 0.0
    capability_recall = (
        found_expected_capabilities / total_expected_capabilities
        if total_expected_capabilities
        else 1.0
    )
    importance_accuracy = (
        correct_expected_importance / total_expected_importance
        if total_expected_importance
        else 1.0
    )
    forbidden_rate = forbidden_case_count / total if total else 0.0
    gate_passed = (
        case_rate >= CASE_PASS_THRESHOLD
        and workflow_rate >= WORKFLOW_SUCCESS_THRESHOLD
        and capability_recall >= CAPABILITY_RECALL_THRESHOLD
        and importance_accuracy >= IMPORTANCE_ACCURACY_THRESHOLD
        and forbidden_rate <= FORBIDDEN_CAPABILITY_RATE_THRESHOLD
    )
    return JobRequirementEvalReport(
        dataset_version=dataset_version,
        total_cases=total,
        passed_cases=passed_cases,
        case_pass_rate=case_rate,
        workflow_success_rate=workflow_rate,
        capability_recall=capability_recall,
        importance_accuracy=importance_accuracy,
        forbidden_capability_rate=forbidden_rate,
        gate_passed=gate_passed,
        cases=tuple(results),
    )


def _capability_equal(actual: str | None, expected: str | None) -> bool:
    if actual is None or expected is None:
        return actual is None and expected is None
    return actual.casefold() == expected.casefold()


def _expected_label(item: ExpectedRequirement) -> str:
    return f"{item.type.value}:{item.normalized_capability or '-'}:{item.importance.value}"

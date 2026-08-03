"""Repeatable Profile Extraction evaluation and versioned quality gate."""
from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from app.application.profile_extraction import ProfileExtractionExecutionError
from app.workflows import ProposeProfileFromResumeWorkflow


class ProfileEvalMode(StrEnum):
    FIXTURE = "fixture"
    LIVE = "live"


@dataclass(frozen=True, slots=True)
class ProfileEvalGate:
    version: str = "profile-eval-gate-v1"
    min_case_pass_rate: float = 0.90
    min_workflow_success_rate: float = 1.0
    min_skill_recall: float = 0.95
    min_years_accuracy: float = 0.90
    max_forbidden_fact_rate: float = 0.0


DEFAULT_PROFILE_EVAL_GATE = ProfileEvalGate()


@dataclass(frozen=True, slots=True)
class ProfileEvalCase:
    id: str
    resume_text: str
    expected_skills: tuple[str, ...]
    expected_years: float | None
    forbidden_terms: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProfileEvalFailure:
    case_id: str
    reason: str


@dataclass(frozen=True, slots=True)
class ProfileEvalCaseResult:
    case_id: str
    trace_run_id: str | None
    workflow_succeeded: bool
    passed: bool
    failure_codes: tuple[str, ...]
    failure_reasons: tuple[str, ...]
    expected_skills: tuple[str, ...]
    actual_skills: tuple[str, ...]
    missing_skills: tuple[str, ...]
    expected_years: float | None
    actual_years: float | None
    forbidden_terms: tuple[str, ...]
    observed_forbidden_terms: tuple[str, ...]
    diagnostics: dict[str, object]


@dataclass(frozen=True, slots=True)
class ProfileEvalMetrics:
    case_pass_rate: float
    workflow_success_rate: float
    skill_recall: float
    years_accuracy: float | None
    forbidden_fact_rate: float


@dataclass(frozen=True, slots=True)
class ProfileEvalReport:
    total: int
    passed: int
    failures: tuple[ProfileEvalFailure, ...]
    case_results: tuple[ProfileEvalCaseResult, ...]
    metrics: ProfileEvalMetrics
    gate_version: str
    gate_passed: bool
    gate_failures: tuple[str, ...]

    @property
    def pass_rate(self) -> float:
        return self.metrics.case_pass_rate


def load_profile_eval_cases(path: Path) -> tuple[ProfileEvalCase, ...]:
    cases = []
    seen_ids: set[str] = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        data = json.loads(line)
        case_id = str(data["id"])
        if case_id in seen_ids:
            raise ValueError(
                f"Duplicate Profile Eval case id {case_id!r} at line {line_number}"
            )
        seen_ids.add(case_id)
        cases.append(
            ProfileEvalCase(
                id=case_id,
                resume_text=str(data["resumeText"]),
                expected_skills=tuple(str(item) for item in data["expectedSkills"]),
                expected_years=(
                    float(data["expectedYears"])
                    if data.get("expectedYears") is not None
                    else None
                ),
                forbidden_terms=tuple(
                    str(item) for item in data.get("forbiddenTerms", [])
                ),
            )
        )
    if not cases:
        raise ValueError(f"No Profile Eval cases found in {path}")
    return tuple(cases)


def run_profile_eval(
    workflow: ProposeProfileFromResumeWorkflow,
    cases: tuple[ProfileEvalCase, ...],
    gate: ProfileEvalGate = DEFAULT_PROFILE_EVAL_GATE,
) -> ProfileEvalReport:
    case_results = tuple(_evaluate_case(workflow, case) for case in cases)
    metrics = _metrics(case_results)
    gate_failures = _gate_failures(metrics, gate)
    failures = tuple(
        ProfileEvalFailure(result.case_id, "; ".join(result.failure_reasons))
        for result in case_results
        if not result.passed
    )
    return ProfileEvalReport(
        total=len(case_results),
        passed=sum(1 for result in case_results if result.passed),
        failures=failures,
        case_results=case_results,
        metrics=metrics,
        gate_version=gate.version,
        gate_passed=not gate_failures,
        gate_failures=gate_failures,
    )


def _evaluate_case(
    workflow: ProposeProfileFromResumeWorkflow,
    case: ProfileEvalCase,
) -> ProfileEvalCaseResult:
    trace_run_id: str | None = None
    workflow_succeeded = False
    actual_skills: tuple[str, ...] = ()
    actual_years: float | None = None
    missing_skills: tuple[str, ...] = case.expected_skills
    observed_forbidden: tuple[str, ...] = ()
    failure_codes: list[str] = []
    failure_reasons: list[str] = []
    diagnostics: dict[str, object] = {}

    try:
        output = workflow.execute(case.resume_text)
        trace_run_id = output.run_id
        workflow_succeeded = True
        actual_skills = tuple(item.name for item in output.skills)
        actual_years = output.years_of_experience
        actual_skill_keys = {item.casefold() for item in actual_skills}
        missing_skills = tuple(
            skill for skill in case.expected_skills if skill.casefold() not in actual_skill_keys
        )
        if missing_skills:
            failure_codes.append("missing_expected_skill")
            failure_reasons.append(
                f"missing expected skills: {', '.join(missing_skills)}"
            )

        if case.expected_years is not None and (
            actual_years is None or abs(actual_years - case.expected_years) > 0.5
        ):
            failure_codes.append("years_out_of_tolerance")
            failure_reasons.append("yearsOfExperience outside 0.5-year tolerance")

        serialized = json.dumps(
            {
                "headline": output.headline,
                "evidence": [item.summary for item in output.evidence],
                "skills": list(actual_skills),
            },
            ensure_ascii=False,
        ).casefold()
        observed_forbidden = tuple(
            term for term in case.forbidden_terms if term.casefold() in serialized
        )
        if observed_forbidden:
            failure_codes.append("forbidden_unsupported_fact")
            failure_reasons.append(
                f"forbidden unsupported facts appeared: {', '.join(observed_forbidden)}"
            )
    except ProfileExtractionExecutionError as error:
        trace_run_id = error.run_id
        failure_codes.append("workflow_execution_failed")
        failure_reasons.append(f"extract/validate failed: {error}")
        diagnostics["errorType"] = type(error).__name__
    except Exception as error:
        failure_codes.append("untraced_eval_failure")
        failure_reasons.append(f"eval failed before a trace was available: {type(error).__name__}")
        diagnostics["errorType"] = type(error).__name__

    return ProfileEvalCaseResult(
        case_id=case.id,
        trace_run_id=trace_run_id,
        workflow_succeeded=workflow_succeeded,
        passed=not failure_codes,
        failure_codes=tuple(failure_codes),
        failure_reasons=tuple(failure_reasons),
        expected_skills=case.expected_skills,
        actual_skills=actual_skills,
        missing_skills=missing_skills,
        expected_years=case.expected_years,
        actual_years=actual_years,
        forbidden_terms=case.forbidden_terms,
        observed_forbidden_terms=observed_forbidden,
        diagnostics=diagnostics,
    )


def _metrics(results: tuple[ProfileEvalCaseResult, ...]) -> ProfileEvalMetrics:
    total = len(results)
    expected_skill_count = sum(len(item.expected_skills) for item in results)
    missing_skill_count = sum(len(item.missing_skills) for item in results)
    years_results = [item for item in results if item.expected_years is not None]
    accurate_years = sum(
        1
        for item in years_results
        if item.actual_years is not None
        and abs(item.actual_years - item.expected_years) <= 0.5  # type: ignore[operator]
    )
    return ProfileEvalMetrics(
        case_pass_rate=(sum(1 for item in results if item.passed) / total if total else 0.0),
        workflow_success_rate=(sum(1 for item in results if item.workflow_succeeded) / total if total else 0.0),
        skill_recall=(
            (expected_skill_count - missing_skill_count) / expected_skill_count
            if expected_skill_count
            else 1.0
        ),
        years_accuracy=(accurate_years / len(years_results) if years_results else None),
        forbidden_fact_rate=(
            sum(1 for item in results if item.observed_forbidden_terms) / total
            if total
            else 0.0
        ),
    )


def _gate_failures(
    metrics: ProfileEvalMetrics,
    gate: ProfileEvalGate,
) -> tuple[str, ...]:
    failures: list[str] = []
    if metrics.case_pass_rate < gate.min_case_pass_rate:
        failures.append("case_pass_rate")
    if metrics.workflow_success_rate < gate.min_workflow_success_rate:
        failures.append("workflow_success_rate")
    if metrics.skill_recall < gate.min_skill_recall:
        failures.append("skill_recall")
    if (
        metrics.years_accuracy is not None
        and metrics.years_accuracy < gate.min_years_accuracy
    ):
        failures.append("years_accuracy")
    if metrics.forbidden_fact_rate > gate.max_forbidden_fact_rate:
        failures.append("forbidden_fact_rate")
    return tuple(failures)

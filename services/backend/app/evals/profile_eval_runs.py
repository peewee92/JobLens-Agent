"""Execute, gate and persist immutable Profile Eval runs."""
from __future__ import annotations

from collections.abc import Callable
from uuid import uuid4

from app.application.ports.profile_eval_repository import AbstractProfileEvalQueryRepository
from app.application.ports.profile_eval_unit_of_work import AbstractProfileEvalUnitOfWork
from app.application.profile_evals import (
    ProfileEvalCaseWrite,
    ProfileEvalRunDetail,
    ProfileEvalRunNotFoundError,
    ProfileEvalRunWrite,
)
from app.evals.profile_extraction import (
    DEFAULT_PROFILE_EVAL_GATE,
    ProfileEvalCase,
    ProfileEvalGate,
    ProfileEvalMode,
    run_profile_eval,
)
from app.workflows import ProposeProfileFromResumeWorkflow
from app.workflows.profile_extraction import EXTRACTOR_VERSION, PROMPT_VERSION

ProfileEvalUnitOfWorkFactory = Callable[[], AbstractProfileEvalUnitOfWork]


class RunProfileEvalUseCase:
    """Run the dataset through the real Workflow and persist one immutable report."""

    def __init__(
        self,
        *,
        workflow: ProposeProfileFromResumeWorkflow,
        eval_uow_factory: ProfileEvalUnitOfWorkFactory,
        query_repository: AbstractProfileEvalQueryRepository,
        dataset_version: str,
        mode: ProfileEvalMode,
        provider: str,
        model: str,
        gate: ProfileEvalGate = DEFAULT_PROFILE_EVAL_GATE,
    ) -> None:
        normalized_provider = provider.strip().lower()
        if mode is ProfileEvalMode.FIXTURE and normalized_provider != "fixture":
            raise ValueError("Fixture Eval mode requires provider='fixture'")
        if mode is ProfileEvalMode.LIVE and normalized_provider == "fixture":
            raise ValueError("Live Eval mode cannot use the fixture provider")
        self._workflow = workflow
        self._eval_uow_factory = eval_uow_factory
        self._query_repository = query_repository
        self._dataset_version = dataset_version
        self._mode = mode
        self._provider = normalized_provider
        self._model = model
        self._gate = gate

    def execute(
        self,
        cases: tuple[ProfileEvalCase, ...],
        *,
        baseline_run_id: str | None = None,
    ) -> ProfileEvalRunDetail:
        if baseline_run_id and self._query_repository.get_summary(baseline_run_id) is None:
            raise ProfileEvalRunNotFoundError(
                f"Baseline Profile Eval Run {baseline_run_id!r} was not found"
            )

        report = run_profile_eval(self._workflow, cases, self._gate)
        eval_run_id = f"eval_{uuid4().hex}"
        write = ProfileEvalRunWrite(
            eval_run_id=eval_run_id,
            dataset_version=self._dataset_version,
            mode=self._mode.value,
            provider=self._provider,
            model=self._model,
            extractor_version=EXTRACTOR_VERSION,
            prompt_version=PROMPT_VERSION,
            gate_version=report.gate_version,
            baseline_run_id=baseline_run_id,
            total_cases=report.total,
            passed_cases=report.passed,
            case_pass_rate=report.metrics.case_pass_rate,
            workflow_success_rate=report.metrics.workflow_success_rate,
            skill_recall=report.metrics.skill_recall,
            years_accuracy=report.metrics.years_accuracy,
            forbidden_fact_rate=report.metrics.forbidden_fact_rate,
            gate_passed=report.gate_passed,
            release_eligible=(
                self._mode is ProfileEvalMode.LIVE and report.gate_passed
            ),
            cases=tuple(
                ProfileEvalCaseWrite(
                    case_id=item.case_id,
                    trace_run_id=item.trace_run_id,
                    workflow_succeeded=item.workflow_succeeded,
                    passed=item.passed,
                    failure_codes=item.failure_codes,
                    failure_reasons=item.failure_reasons,
                    expected_skills=item.expected_skills,
                    actual_skills=item.actual_skills,
                    missing_skills=item.missing_skills,
                    expected_years=item.expected_years,
                    actual_years=item.actual_years,
                    forbidden_terms=item.forbidden_terms,
                    observed_forbidden_terms=item.observed_forbidden_terms,
                    diagnostics=item.diagnostics,
                )
                for item in report.case_results
            ),
        )
        with self._eval_uow_factory() as uow:
            uow.eval_runs.add(write)
            uow.commit()

        detail = self._query_repository.get_run(eval_run_id)
        if detail is None:  # pragma: no cover - defensive persistence invariant
            raise RuntimeError(f"Persisted Profile Eval Run {eval_run_id} cannot be read")
        return detail

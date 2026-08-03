"""Execute, gate and persist immutable Requirement Eval runs."""
from __future__ import annotations

from collections.abc import Callable
from uuid import uuid4

from app.application.ports.requirement_eval_repository import (
    AbstractRequirementEvalQueryRepository,
)
from app.application.ports.requirement_eval_unit_of_work import (
    AbstractRequirementEvalUnitOfWork,
)
from app.application.requirement_evals import (
    RequirementEvalCaseWrite,
    RequirementEvalRunDetail,
    RequirementEvalRunNotFoundError,
    RequirementEvalRunWrite,
)
from app.evals.job_requirement_extraction import (
    JobRequirementEvalCase,
    RequirementEvalMode,
    run_job_requirement_eval,
)
from app.workflows import ExtractJobRequirementsWorkflow
from app.workflows.job_requirement_extraction import EXTRACTOR_VERSION, PROMPT_VERSION

RequirementEvalUnitOfWorkFactory = Callable[[], AbstractRequirementEvalUnitOfWork]


class RunRequirementEvalUseCase:
    """Run the dataset through the real Workflow and persist one immutable report."""

    def __init__(
        self,
        *,
        workflow: ExtractJobRequirementsWorkflow,
        eval_uow_factory: RequirementEvalUnitOfWorkFactory,
        query_repository: AbstractRequirementEvalQueryRepository,
        dataset_version: str,
        mode: RequirementEvalMode,
        provider: str,
        model: str,
    ) -> None:
        normalized_provider = provider.strip().lower()
        if mode is RequirementEvalMode.FIXTURE and normalized_provider != "fixture":
            raise ValueError("Fixture Requirement Eval mode requires provider='fixture'")
        if mode is RequirementEvalMode.LIVE and normalized_provider == "fixture":
            raise ValueError("Live Requirement Eval mode cannot use the fixture provider")
        self._workflow = workflow
        self._eval_uow_factory = eval_uow_factory
        self._query_repository = query_repository
        self._dataset_version = dataset_version
        self._mode = mode
        self._provider = normalized_provider
        self._model = model

    def execute(
        self,
        cases: tuple[JobRequirementEvalCase, ...],
        *,
        baseline_run_id: str | None = None,
    ) -> RequirementEvalRunDetail:
        if baseline_run_id and self._query_repository.get_summary(baseline_run_id) is None:
            raise RequirementEvalRunNotFoundError(
                f"Baseline Requirement Eval Run {baseline_run_id!r} was not found"
            )

        report = run_job_requirement_eval(
            workflow=self._workflow,
            cases=cases,
            dataset_version=self._dataset_version,
        )
        eval_run_id = f"reqeval_{uuid4().hex}"
        write = RequirementEvalRunWrite(
            eval_run_id=eval_run_id,
            dataset_version=report.dataset_version,
            mode=self._mode.value,
            provider=self._provider,
            model=self._model,
            extractor_version=EXTRACTOR_VERSION,
            prompt_version=PROMPT_VERSION,
            gate_version=report.gate_version,
            baseline_run_id=baseline_run_id,
            total_cases=report.total_cases,
            passed_cases=report.passed_cases,
            case_pass_rate=report.case_pass_rate,
            workflow_success_rate=report.workflow_success_rate,
            capability_recall=report.capability_recall,
            importance_accuracy=report.importance_accuracy,
            forbidden_capability_rate=report.forbidden_capability_rate,
            gate_passed=report.gate_passed,
            release_eligible=(
                self._mode is RequirementEvalMode.LIVE and report.gate_passed
            ),
            cases=tuple(
                RequirementEvalCaseWrite(
                    case_id=item.case_id,
                    trace_run_id=item.trace_run_id,
                    workflow_succeeded=item.workflow_succeeded,
                    passed=item.passed,
                    missing_requirements=item.missing_requirements,
                    wrong_importance=item.wrong_importance,
                    observed_forbidden_capabilities=(
                        item.observed_forbidden_capabilities
                    ),
                    actual_requirements=item.actual_requirements,
                    error=item.error,
                )
                for item in report.cases
            ),
        )
        with self._eval_uow_factory() as uow:
            uow.eval_runs.add(write)
            uow.commit()

        detail = self._query_repository.get_run(eval_run_id)
        if detail is None:  # pragma: no cover - defensive persistence invariant
            raise RuntimeError(
                f"Persisted Requirement Eval Run {eval_run_id} cannot be read"
            )
        return detail

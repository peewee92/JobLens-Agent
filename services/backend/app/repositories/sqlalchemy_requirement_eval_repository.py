"""SQLAlchemy persistence for immutable Requirement Eval runs."""
from __future__ import annotations

from collections.abc import Callable
from datetime import timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.application.ports.requirement_eval_repository import (
    AbstractRequirementEvalQueryRepository,
    AbstractRequirementEvalRepository,
)
from app.application.requirement_evals.models import (
    RequirementEvalCaseDetail,
    RequirementEvalMetricComparison,
    RequirementEvalRunDetail,
    RequirementEvalRunPage,
    RequirementEvalRunSummary,
    RequirementEvalRunWrite,
)
from app.db.models import RequirementEvalCaseResultORM, RequirementEvalRunORM

SessionFactory = Callable[[], Session]


class SqlAlchemyRequirementEvalRepository(AbstractRequirementEvalRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, run: RequirementEvalRunWrite) -> None:
        record = RequirementEvalRunORM(
            id=run.eval_run_id,
            dataset_version=run.dataset_version,
            mode=run.mode,
            provider=run.provider,
            model=run.model,
            extractor_version=run.extractor_version,
            prompt_version=run.prompt_version,
            gate_version=run.gate_version,
            baseline_run_id=run.baseline_run_id,
            total_cases=run.total_cases,
            passed_cases=run.passed_cases,
            case_pass_rate=run.case_pass_rate,
            workflow_success_rate=run.workflow_success_rate,
            capability_recall=run.capability_recall,
            importance_accuracy=run.importance_accuracy,
            forbidden_capability_rate=run.forbidden_capability_rate,
            gate_passed=run.gate_passed,
            release_eligible=run.release_eligible,
        )
        record.cases.extend(
            RequirementEvalCaseResultORM(
                case_id=item.case_id,
                trace_run_id=item.trace_run_id,
                workflow_succeeded=item.workflow_succeeded,
                passed=item.passed,
                missing_requirements=list(item.missing_requirements),
                wrong_importance=list(item.wrong_importance),
                observed_forbidden_capabilities=list(
                    item.observed_forbidden_capabilities
                ),
                actual_requirements=list(item.actual_requirements),
                error=item.error,
            )
            for item in run.cases
        )
        self._session.add(record)
        self._session.flush()


class SqlAlchemyRequirementEvalQueryRepository(
    AbstractRequirementEvalQueryRepository
):
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def list_runs(self, *, limit: int, offset: int) -> RequirementEvalRunPage:
        with self._session_factory() as session:
            total = int(
                session.scalar(select(func.count()).select_from(RequirementEvalRunORM))
                or 0
            )
            records = session.scalars(
                select(RequirementEvalRunORM)
                .order_by(
                    RequirementEvalRunORM.created_at.desc(),
                    RequirementEvalRunORM.id.asc(),
                )
                .limit(limit)
                .offset(offset)
            ).all()
            return RequirementEvalRunPage(
                total=total,
                limit=limit,
                offset=offset,
                items=tuple(_summary(record) for record in records),
            )

    def get_run(self, eval_run_id: str) -> RequirementEvalRunDetail | None:
        with self._session_factory() as session:
            record = session.get(RequirementEvalRunORM, eval_run_id)
            if record is None:
                return None
            cases = session.scalars(
                select(RequirementEvalCaseResultORM)
                .where(RequirementEvalCaseResultORM.eval_run_id == eval_run_id)
                .order_by(RequirementEvalCaseResultORM.case_id.asc())
            ).all()
            baseline = (
                session.get(RequirementEvalRunORM, record.baseline_run_id)
                if record.baseline_run_id
                else None
            )
            return RequirementEvalRunDetail(
                summary=_summary(record),
                cases=tuple(_case_detail(item) for item in cases),
                comparison=(
                    _comparison(record, baseline) if baseline is not None else None
                ),
            )

    def get_summary(self, eval_run_id: str) -> RequirementEvalRunSummary | None:
        with self._session_factory() as session:
            record = session.get(RequirementEvalRunORM, eval_run_id)
            return _summary(record) if record is not None else None


def _summary(record: RequirementEvalRunORM) -> RequirementEvalRunSummary:
    return RequirementEvalRunSummary(
        id=record.id,
        dataset_version=record.dataset_version,
        mode=record.mode,
        provider=record.provider,
        model=record.model,
        extractor_version=record.extractor_version,
        prompt_version=record.prompt_version,
        gate_version=record.gate_version,
        baseline_run_id=record.baseline_run_id,
        total_cases=record.total_cases,
        passed_cases=record.passed_cases,
        case_pass_rate=record.case_pass_rate,
        workflow_success_rate=record.workflow_success_rate,
        capability_recall=record.capability_recall,
        importance_accuracy=record.importance_accuracy,
        forbidden_capability_rate=record.forbidden_capability_rate,
        gate_passed=record.gate_passed,
        release_eligible=record.release_eligible,
        created_at=(
            record.created_at.replace(tzinfo=timezone.utc)
            if record.created_at.tzinfo is None
            else record.created_at.astimezone(timezone.utc)
        ),
    )


def _case_detail(record: RequirementEvalCaseResultORM) -> RequirementEvalCaseDetail:
    return RequirementEvalCaseDetail(
        case_id=record.case_id,
        trace_run_id=record.trace_run_id,
        workflow_succeeded=record.workflow_succeeded,
        passed=record.passed,
        missing_requirements=tuple(record.missing_requirements),
        wrong_importance=tuple(record.wrong_importance),
        observed_forbidden_capabilities=tuple(
            record.observed_forbidden_capabilities
        ),
        actual_requirements=tuple(record.actual_requirements),
        error=record.error,
    )


def _comparison(
    current: RequirementEvalRunORM,
    baseline: RequirementEvalRunORM,
) -> RequirementEvalMetricComparison:
    return RequirementEvalMetricComparison(
        baseline_run_id=baseline.id,
        case_pass_rate_delta=current.case_pass_rate - baseline.case_pass_rate,
        workflow_success_rate_delta=(
            current.workflow_success_rate - baseline.workflow_success_rate
        ),
        capability_recall_delta=(
            current.capability_recall - baseline.capability_recall
        ),
        importance_accuracy_delta=(
            current.importance_accuracy - baseline.importance_accuracy
        ),
        forbidden_capability_rate_delta=(
            current.forbidden_capability_rate
            - baseline.forbidden_capability_rate
        ),
    )

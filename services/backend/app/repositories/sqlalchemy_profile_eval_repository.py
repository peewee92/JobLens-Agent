"""SQLAlchemy persistence for immutable Profile Eval runs."""
from __future__ import annotations

from collections.abc import Callable
from datetime import timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.application.ports.profile_eval_repository import (
    AbstractProfileEvalQueryRepository,
    AbstractProfileEvalRepository,
)
from app.application.profile_evals.models import (
    AcceptedProfileEvalBaseline,
    ProfileEvalCaseDetail,
    ProfileEvalMetricComparison,
    ProfileEvalReviewDecision,
    ProfileEvalReviewDetail,
    ProfileEvalRunDetail,
    ProfileEvalRunPage,
    ProfileEvalRunSummary,
    ProfileEvalRunWrite,
)
from app.db.models import (
    ProfileEvalCaseResultORM,
    ProfileEvalReviewORM,
    ProfileEvalRunORM,
)

SessionFactory = Callable[[], Session]


class SqlAlchemyProfileEvalRepository(AbstractProfileEvalRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, run: ProfileEvalRunWrite) -> None:
        record = ProfileEvalRunORM(
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
            skill_recall=run.skill_recall,
            years_accuracy=run.years_accuracy,
            forbidden_fact_rate=run.forbidden_fact_rate,
            gate_passed=run.gate_passed,
            release_eligible=run.release_eligible,
        )
        record.cases.extend(
            ProfileEvalCaseResultORM(
                case_id=item.case_id,
                trace_run_id=item.trace_run_id,
                workflow_succeeded=item.workflow_succeeded,
                passed=item.passed,
                failure_codes=list(item.failure_codes),
                failure_reasons=list(item.failure_reasons),
                expected_skills=list(item.expected_skills),
                actual_skills=list(item.actual_skills),
                missing_skills=list(item.missing_skills),
                expected_years=item.expected_years,
                actual_years=item.actual_years,
                forbidden_terms=list(item.forbidden_terms),
                observed_forbidden_terms=list(item.observed_forbidden_terms),
                diagnostics=dict(item.diagnostics),
            )
            for item in run.cases
        )
        self._session.add(record)
        self._session.flush()


class SqlAlchemyProfileEvalQueryRepository(AbstractProfileEvalQueryRepository):
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def list_runs(self, *, limit: int, offset: int) -> ProfileEvalRunPage:
        with self._session_factory() as session:
            total = int(
                session.scalar(select(func.count()).select_from(ProfileEvalRunORM))
                or 0
            )
            records = session.scalars(
                select(ProfileEvalRunORM)
                .order_by(ProfileEvalRunORM.created_at.desc(), ProfileEvalRunORM.id.asc())
                .limit(limit)
                .offset(offset)
            ).all()
            return ProfileEvalRunPage(
                total=total,
                limit=limit,
                offset=offset,
                items=tuple(_summary(record) for record in records),
            )

    def get_run(self, eval_run_id: str) -> ProfileEvalRunDetail | None:
        with self._session_factory() as session:
            record = session.get(ProfileEvalRunORM, eval_run_id)
            if record is None:
                return None
            cases = session.scalars(
                select(ProfileEvalCaseResultORM)
                .where(ProfileEvalCaseResultORM.eval_run_id == eval_run_id)
                .order_by(ProfileEvalCaseResultORM.case_id.asc())
            ).all()
            baseline = (
                session.get(ProfileEvalRunORM, record.baseline_run_id)
                if record.baseline_run_id
                else None
            )
            review = session.scalar(
                select(ProfileEvalReviewORM).where(
                    ProfileEvalReviewORM.eval_run_id == eval_run_id
                )
            )
            return ProfileEvalRunDetail(
                summary=_summary(record),
                cases=tuple(_case_detail(item) for item in cases),
                comparison=(
                    _comparison(record, baseline) if baseline is not None else None
                ),
                review=_review_detail(review) if review is not None else None,
            )

    def get_summary(self, eval_run_id: str) -> ProfileEvalRunSummary | None:
        with self._session_factory() as session:
            record = session.get(ProfileEvalRunORM, eval_run_id)
            return _summary(record) if record is not None else None

    def get_review(self, eval_run_id: str) -> ProfileEvalReviewDetail | None:
        with self._session_factory() as session:
            record = session.scalar(
                select(ProfileEvalReviewORM).where(
                    ProfileEvalReviewORM.eval_run_id == eval_run_id
                )
            )
            return _review_detail(record) if record is not None else None

    def get_accepted_baseline(self) -> AcceptedProfileEvalBaseline | None:
        with self._session_factory() as session:
            row = session.execute(
                select(ProfileEvalReviewORM, ProfileEvalRunORM)
                .join(
                    ProfileEvalRunORM,
                    ProfileEvalRunORM.id == ProfileEvalReviewORM.eval_run_id,
                )
                .where(
                    ProfileEvalReviewORM.decision
                    == ProfileEvalReviewDecision.ACCEPTED.value,
                    ProfileEvalRunORM.mode == "live",
                    ProfileEvalRunORM.gate_passed.is_(True),
                    ProfileEvalRunORM.release_eligible.is_(True),
                )
                .order_by(
                    ProfileEvalReviewORM.reviewed_at.desc(),
                    ProfileEvalReviewORM.id.desc(),
                )
                .limit(1)
            ).first()
            if row is None:
                return None
            review, run = row
            return AcceptedProfileEvalBaseline(
                review=_review_detail(review),
                run=_summary(run),
            )


def _summary(record: ProfileEvalRunORM) -> ProfileEvalRunSummary:
    return ProfileEvalRunSummary(
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
        skill_recall=record.skill_recall,
        years_accuracy=record.years_accuracy,
        forbidden_fact_rate=record.forbidden_fact_rate,
        gate_passed=record.gate_passed,
        release_eligible=record.release_eligible,
        created_at=(
            record.created_at.replace(tzinfo=timezone.utc)
            if record.created_at.tzinfo is None
            else record.created_at.astimezone(timezone.utc)
        ),
    )


def _review_detail(record: ProfileEvalReviewORM) -> ProfileEvalReviewDetail:
    return ProfileEvalReviewDetail(
        id=record.id,
        eval_run_id=record.eval_run_id,
        decision=ProfileEvalReviewDecision(record.decision),
        reviewer=record.reviewer,
        notes=record.notes,
        reviewed_at=(
            record.reviewed_at.replace(tzinfo=timezone.utc)
            if record.reviewed_at.tzinfo is None
            else record.reviewed_at.astimezone(timezone.utc)
        ),
    )


def _case_detail(record: ProfileEvalCaseResultORM) -> ProfileEvalCaseDetail:
    return ProfileEvalCaseDetail(
        case_id=record.case_id,
        trace_run_id=record.trace_run_id,
        workflow_succeeded=record.workflow_succeeded,
        passed=record.passed,
        failure_codes=tuple(record.failure_codes),
        failure_reasons=tuple(record.failure_reasons),
        expected_skills=tuple(record.expected_skills),
        actual_skills=tuple(record.actual_skills),
        missing_skills=tuple(record.missing_skills),
        expected_years=record.expected_years,
        actual_years=record.actual_years,
        forbidden_terms=tuple(record.forbidden_terms),
        observed_forbidden_terms=tuple(record.observed_forbidden_terms),
        diagnostics=dict(record.diagnostics),
    )


def _comparison(
    current: ProfileEvalRunORM,
    baseline: ProfileEvalRunORM,
) -> ProfileEvalMetricComparison:
    years_delta = (
        current.years_accuracy - baseline.years_accuracy
        if current.years_accuracy is not None and baseline.years_accuracy is not None
        else None
    )
    return ProfileEvalMetricComparison(
        baseline_run_id=baseline.id,
        case_pass_rate_delta=current.case_pass_rate - baseline.case_pass_rate,
        workflow_success_rate_delta=(
            current.workflow_success_rate - baseline.workflow_success_rate
        ),
        skill_recall_delta=current.skill_recall - baseline.skill_recall,
        years_accuracy_delta=years_delta,
        forbidden_fact_rate_delta=(
            current.forbidden_fact_rate - baseline.forbidden_fact_rate
        ),
    )

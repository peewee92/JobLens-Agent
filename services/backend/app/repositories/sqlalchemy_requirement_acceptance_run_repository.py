"""SQLAlchemy persistence for controlled Requirement acceptance runs."""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from hashlib import sha256

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.application.ports.requirement_acceptance_run_repository import (
    AbstractRequirementAcceptanceRunQueryRepository,
    AbstractRequirementAcceptanceRunRepository,
)
from app.application.requirement_acceptance.errors import (
    RequirementAcceptanceCanaryReviewAlreadyExistsError,
)
from app.application.requirement_acceptance.runs import (
    RequirementAcceptanceCanaryDecision,
    RequirementAcceptanceCanaryReviewDetail,
    RequirementAcceptanceCanaryReviewWrite,
    RequirementAcceptanceRunCaseDetail,
    RequirementAcceptanceRunCaseStatus,
    RequirementAcceptanceRunCaseUpdate,
    RequirementAcceptanceRunDetail,
    RequirementAcceptanceRunPage,
    RequirementAcceptanceRunStatus,
    RequirementAcceptanceRunSummary,
    RequirementAcceptanceRunWrite,
)
from app.db.models import (
    RequirementAcceptanceCanaryReviewORM,
    RequirementAcceptanceExecutionLeaseORM,
    RequirementAcceptanceRunCaseORM,
    RequirementAcceptanceRunORM,
)
from app.db.models.common import utc_now

SessionFactory = Callable[[], Session]


class SqlAlchemyRequirementAcceptanceRunRepository(
    AbstractRequirementAcceptanceRunRepository
):
    def __init__(self, session: Session) -> None:
        self._session = session

    def add_run(self, run: RequirementAcceptanceRunWrite) -> None:
        record = RequirementAcceptanceRunORM(
            id=run.run_id,
            dataset_fingerprint=run.dataset_fingerprint,
            source_version=run.source_version,
            dataset_generated_at=run.dataset_generated_at,
            title=run.title,
            reviewer=run.reviewer,
            provider=run.provider,
            model=run.model,
            extractor_version=run.extractor_version,
            prompt_version=run.prompt_version,
            first_import_id=run.first_import_id,
            last_import_id=run.last_import_id,
            total_cases=len(run.cases),
        )
        record.cases.extend(
            RequirementAcceptanceRunCaseORM(
                id=item.case_id,
                case_index=item.case_index,
                source_url=item.source_url,
                title=item.title,
                company=item.company,
                description_hash=item.description_hash,
                description_snapshot=item.description_snapshot,
                job_id=item.job_id,
                status=RequirementAcceptanceRunCaseStatus.PENDING.value,
                attempt_count=0,
            )
            for item in run.cases
        )
        self._session.add(record)
        self._session.flush()

    def try_acquire_execution_lease(
        self,
        *,
        identity_key: str,
        lease_token: str,
        acquired_at: datetime,
        expires_at: datetime,
    ) -> bool:
        reclaimed = self._session.execute(
            update(RequirementAcceptanceExecutionLeaseORM)
            .where(
                RequirementAcceptanceExecutionLeaseORM.identity_key == identity_key,
                RequirementAcceptanceExecutionLeaseORM.expires_at <= acquired_at,
            )
            .values(
                lease_token=lease_token,
                acquired_at=acquired_at,
                expires_at=expires_at,
                updated_at=acquired_at,
            )
        )
        if reclaimed.rowcount == 1:
            self._session.flush()
            return True

        try:
            with self._session.begin_nested():
                self._session.add(
                    RequirementAcceptanceExecutionLeaseORM(
                        identity_key=identity_key,
                        lease_token=lease_token,
                        acquired_at=acquired_at,
                        expires_at=expires_at,
                        created_at=acquired_at,
                        updated_at=acquired_at,
                    )
                )
                self._session.flush()
        except IntegrityError:
            return False
        return True

    def renew_execution_lease(
        self,
        *,
        identity_key: str,
        lease_token: str,
        renewed_at: datetime,
        expires_at: datetime,
    ) -> bool:
        renewed = self._session.execute(
            update(RequirementAcceptanceExecutionLeaseORM)
            .where(
                RequirementAcceptanceExecutionLeaseORM.identity_key == identity_key,
                RequirementAcceptanceExecutionLeaseORM.lease_token == lease_token,
                RequirementAcceptanceExecutionLeaseORM.expires_at > renewed_at,
            )
            .values(
                expires_at=expires_at,
                updated_at=renewed_at,
            )
        )
        self._session.flush()
        return renewed.rowcount == 1

    def release_execution_lease(
        self,
        *,
        identity_key: str,
        lease_token: str,
    ) -> bool:
        released = self._session.execute(
            delete(RequirementAcceptanceExecutionLeaseORM).where(
                RequirementAcceptanceExecutionLeaseORM.identity_key == identity_key,
                RequirementAcceptanceExecutionLeaseORM.lease_token == lease_token,
            )
        )
        self._session.flush()
        return released.rowcount == 1

    def update_last_import(
        self,
        *,
        run_id: str,
        import_id: str,
        dataset_generated_at: str | None,
    ) -> None:
        record = self._required_run(run_id)
        record.last_import_id = import_id
        record.dataset_generated_at = dataset_generated_at
        record.updated_at = utc_now()
        self._session.flush()

    def update_case(self, update: RequirementAcceptanceRunCaseUpdate) -> None:
        record = self._session.scalar(
            select(RequirementAcceptanceRunCaseORM).where(
                RequirementAcceptanceRunCaseORM.run_id == update.run_id,
                RequirementAcceptanceRunCaseORM.case_index == update.case_index,
            )
        )
        if record is None:
            raise RuntimeError(
                f"Requirement acceptance run case {update.run_id}:{update.case_index} was not found"
            )
        preserve_prior_failure = (
            update.status is RequirementAcceptanceRunCaseStatus.DEFERRED
            and record.status == RequirementAcceptanceRunCaseStatus.FAILED.value
        )
        next_status = update.status.value
        if (
            update.status is RequirementAcceptanceRunCaseStatus.REUSED
            and record.status == RequirementAcceptanceRunCaseStatus.EXTRACTED.value
        ):
            # Invocation-level reuse must not erase that this Run originally paid
            # for and created the Extraction in an earlier canary/resume step.
            next_status = RequirementAcceptanceRunCaseStatus.EXTRACTED.value
        record.job_id = update.job_id
        record.attempt_count += update.attempt_increment
        if not preserve_prior_failure:
            record.status = next_status
            record.extraction_id = update.extraction_id
            record.trace_run_id = update.trace_run_id
            record.error_code = update.error_code
            record.error_message = (
                update.error_message[:2000]
                if update.error_message is not None
                else None
            )
        record.updated_at = utc_now()
        run = self._required_run(update.run_id)
        run.updated_at = record.updated_at
        self._session.flush()

    def attach_batch(self, *, run_id: str, batch_id: str) -> None:
        record = self._required_run(run_id)
        if record.batch_id is not None and record.batch_id != batch_id:
            raise RuntimeError(
                f"Requirement acceptance run {run_id!r} already references another Batch"
            )
        record.batch_id = batch_id
        record.updated_at = utc_now()
        self._session.flush()

    def add_canary_review(
        self,
        review: RequirementAcceptanceCanaryReviewWrite,
    ) -> None:
        record = RequirementAcceptanceCanaryReviewORM(
            id=review.review_id,
            run_id=review.run_id,
            reviewer=review.reviewer,
            decision=review.decision.value,
            notes=review.notes,
            reviewed_case_ids=list(review.reviewed_case_ids),
            reviewed_extraction_ids=list(review.reviewed_extraction_ids),
            reviewed_trace_run_ids=list(review.reviewed_trace_run_ids),
            reviewed_at=review.reviewed_at,
        )
        self._session.add(record)
        try:
            self._session.flush()
        except IntegrityError as error:
            message = str(error.orig).casefold()
            if (
                "requirement_acceptance_canary_reviews.run_id" in message
                or "uq_requirement_acceptance_canary_reviews_run_id" in message
            ):
                raise RequirementAcceptanceCanaryReviewAlreadyExistsError(
                    f"Requirement acceptance run {review.run_id!r} already has an immutable Canary review"
                ) from error
            raise

    def _required_run(self, run_id: str) -> RequirementAcceptanceRunORM:
        record = self._session.get(RequirementAcceptanceRunORM, run_id)
        if record is None:
            raise RuntimeError(f"Requirement acceptance run {run_id!r} was not found")
        return record


class SqlAlchemyRequirementAcceptanceRunQueryRepository(
    AbstractRequirementAcceptanceRunQueryRepository
):
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def list_runs(self, *, limit: int, offset: int) -> RequirementAcceptanceRunPage:
        with self._session_factory() as session:
            total = int(
                session.scalar(
                    select(func.count()).select_from(RequirementAcceptanceRunORM)
                )
                or 0
            )
            records = session.scalars(
                select(RequirementAcceptanceRunORM)
                .options(*_run_load_options())
                .order_by(
                    RequirementAcceptanceRunORM.updated_at.desc(),
                    RequirementAcceptanceRunORM.id.asc(),
                )
                .limit(limit)
                .offset(offset)
            ).all()
            details = tuple(_run_detail(record) for record in records)
            return RequirementAcceptanceRunPage(
                total=total,
                limit=limit,
                offset=offset,
                items=tuple(_run_summary(detail) for detail in details),
            )

    def get_by_identity(
        self,
        *,
        dataset_fingerprint: str,
        title: str,
        reviewer: str,
        provider: str,
        model: str,
        extractor_version: str,
        prompt_version: str,
    ) -> RequirementAcceptanceRunDetail | None:
        with self._session_factory() as session:
            record = session.scalar(
                select(RequirementAcceptanceRunORM)
                .options(*_run_load_options())
                .where(
                    RequirementAcceptanceRunORM.dataset_fingerprint
                    == dataset_fingerprint,
                    RequirementAcceptanceRunORM.title == title,
                    RequirementAcceptanceRunORM.reviewer == reviewer,
                    RequirementAcceptanceRunORM.provider == provider,
                    RequirementAcceptanceRunORM.model == model,
                    RequirementAcceptanceRunORM.extractor_version
                    == extractor_version,
                    RequirementAcceptanceRunORM.prompt_version == prompt_version,
                )
            )
            return _run_detail(record) if record is not None else None

    def get_run(self, run_id: str) -> RequirementAcceptanceRunDetail | None:
        with self._session_factory() as session:
            record = session.scalar(
                select(RequirementAcceptanceRunORM)
                .options(*_run_load_options())
                .where(RequirementAcceptanceRunORM.id == run_id)
            )
            return _run_detail(record) if record is not None else None

    def get_canary_review(
        self,
        run_id: str,
    ) -> RequirementAcceptanceCanaryReviewDetail | None:
        with self._session_factory() as session:
            record = session.scalar(
                select(RequirementAcceptanceCanaryReviewORM).where(
                    RequirementAcceptanceCanaryReviewORM.run_id == run_id
                )
            )
            return _canary_review_detail(record) if record is not None else None


def _run_detail(record: RequirementAcceptanceRunORM) -> RequirementAcceptanceRunDetail:
    cases = tuple(
        _run_case_detail(item)
        for item in sorted(record.cases, key=lambda case: case.case_index)
    )
    counts = {
        status: sum(case.status is status for case in cases)
        for status in RequirementAcceptanceRunCaseStatus
    }
    canary_review = (
        _canary_review_detail(record.canary_review)
        if record.canary_review is not None
        else None
    )
    attempted_calls = sum(case.attempt_count for case in cases)
    canary_review_required = (
        record.provider.casefold() == "openai"
        and attempted_calls >= 3
        and canary_review is None
        and record.batch_id is None
    )
    if record.batch_id is not None and (
        counts[RequirementAcceptanceRunCaseStatus.REUSED]
        + counts[RequirementAcceptanceRunCaseStatus.EXTRACTED]
        == record.total_cases
    ):
        status = RequirementAcceptanceRunStatus.READY
    elif (
        canary_review is not None
        and canary_review.decision is RequirementAcceptanceCanaryDecision.STOP
    ):
        status = RequirementAcceptanceRunStatus.STOPPED
    elif canary_review_required:
        status = RequirementAcceptanceRunStatus.AWAITING_CANARY_REVIEW
    elif counts[RequirementAcceptanceRunCaseStatus.PENDING] == record.total_cases:
        status = RequirementAcceptanceRunStatus.PENDING
    else:
        status = RequirementAcceptanceRunStatus.PARTIAL
    return RequirementAcceptanceRunDetail(
        id=record.id,
        dataset_fingerprint=record.dataset_fingerprint,
        source_version=record.source_version,
        dataset_generated_at=record.dataset_generated_at,
        title=record.title,
        reviewer=record.reviewer,
        provider=record.provider,
        model=record.model,
        extractor_version=record.extractor_version,
        prompt_version=record.prompt_version,
        first_import_id=record.first_import_id,
        last_import_id=record.last_import_id,
        batch_id=record.batch_id,
        status=status,
        canary_review_required=canary_review_required,
        canary_review=canary_review,
        pending_count=counts[RequirementAcceptanceRunCaseStatus.PENDING],
        reused_count=counts[RequirementAcceptanceRunCaseStatus.REUSED],
        extracted_count=counts[RequirementAcceptanceRunCaseStatus.EXTRACTED],
        failed_count=counts[RequirementAcceptanceRunCaseStatus.FAILED],
        deferred_count=counts[RequirementAcceptanceRunCaseStatus.DEFERRED],
        attempted_calls=attempted_calls,
        created_at=_utc(record.created_at),
        updated_at=_utc(record.updated_at),
        cases=cases,
    )


def _run_case_detail(
    item: RequirementAcceptanceRunCaseORM,
) -> RequirementAcceptanceRunCaseDetail:
    current_description_hash = _description_hash(item.job.description)
    trace = item.trace
    return RequirementAcceptanceRunCaseDetail(
        id=item.id,
        case_index=item.case_index,
        source_url=item.source_url,
        title=item.title,
        company=item.company,
        description_hash=item.description_hash,
        description_snapshot=item.description_snapshot,
        current_description_hash=current_description_hash,
        description_is_current=current_description_hash == item.description_hash,
        job_id=item.job_id,
        status=RequirementAcceptanceRunCaseStatus(item.status),
        attempt_count=item.attempt_count,
        extraction_id=item.extraction_id,
        trace_run_id=item.trace_run_id,
        trace_capability=trace.capability if trace is not None else None,
        trace_model=trace.model if trace is not None else None,
        trace_prompt_version=trace.prompt_version if trace is not None else None,
        trace_latency_ms=trace.latency_ms if trace is not None else None,
        trace_input_tokens=trace.input_tokens if trace is not None else None,
        trace_output_tokens=trace.output_tokens if trace is not None else None,
        trace_error=_bounded_text(trace.error) if trace is not None else None,
        trace_created_at=_utc(trace.created_at) if trace is not None else None,
        error_code=item.error_code,
        error_message=_bounded_text(item.error_message),
        created_at=_utc(item.created_at),
        updated_at=_utc(item.updated_at),
    )


def _description_hash(description: str | None) -> str:
    return sha256((description or "").strip().encode("utf-8")).hexdigest()


def _bounded_text(value: str | None, limit: int = 2000) -> str | None:
    return value[:limit] if value is not None else None


def _run_summary(
    detail: RequirementAcceptanceRunDetail,
) -> RequirementAcceptanceRunSummary:
    return RequirementAcceptanceRunSummary(
        id=detail.id,
        title=detail.title,
        reviewer=detail.reviewer,
        provider=detail.provider,
        model=detail.model,
        extractor_version=detail.extractor_version,
        prompt_version=detail.prompt_version,
        status=detail.status,
        attempted_calls=detail.attempted_calls,
        completed_case_count=detail.completed_case_count,
        failed_count=detail.failed_count,
        deferred_count=detail.deferred_count,
        canary_review_required=detail.canary_review_required,
        canary_decision=(
            detail.canary_review.decision if detail.canary_review is not None else None
        ),
        batch_id=detail.batch_id,
        created_at=detail.created_at,
        updated_at=detail.updated_at,
    )


def _run_load_options():
    return (
        selectinload(RequirementAcceptanceRunORM.cases).selectinload(
            RequirementAcceptanceRunCaseORM.trace
        ),
        selectinload(RequirementAcceptanceRunORM.cases).selectinload(
            RequirementAcceptanceRunCaseORM.job
        ),
        selectinload(RequirementAcceptanceRunORM.canary_review),
    )


def _canary_review_detail(
    record: RequirementAcceptanceCanaryReviewORM,
) -> RequirementAcceptanceCanaryReviewDetail:
    return RequirementAcceptanceCanaryReviewDetail(
        id=record.id,
        run_id=record.run_id,
        reviewer=record.reviewer,
        decision=RequirementAcceptanceCanaryDecision(record.decision),
        notes=record.notes,
        reviewed_case_ids=tuple(record.reviewed_case_ids or []),
        reviewed_extraction_ids=tuple(record.reviewed_extraction_ids or []),
        reviewed_trace_run_ids=tuple(record.reviewed_trace_run_ids or []),
        reviewed_at=_utc(record.reviewed_at),
    )


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)

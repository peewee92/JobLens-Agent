"""SQLAlchemy persistence/read models for Requirement manual review batches."""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from datetime import timezone
from hashlib import sha256

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.application.job_requirements import JobRequirementDetail
from app.application.ports.requirement_review_repository import (
    AbstractRequirementReviewQueryRepository,
    AbstractRequirementReviewRepository,
)
from app.application.requirement_reviews.errors import (
    RequirementReviewBatchFinalDecisionAlreadyExistsError,
    RequirementReviewCaseAlreadyReviewedError,
)
from app.application.requirement_reviews.models import (
    AcceptedRequirementReviewBaseline,
    RequirementReviewBatchCaseDetail,
    RequirementReviewBatchFinalDecision,
    RequirementReviewBatchFinalDecisionDetail,
    RequirementReviewBatchFinalDecisionWrite,
    RequirementReviewBatchCaseLookup,
    RequirementReviewBatchDetail,
    RequirementReviewBatchPage,
    RequirementReviewBatchSummary,
    RequirementReviewBatchWrite,
    RequirementReviewCandidate,
    RequirementReviewCandidatePage,
    RequirementReviewCaseReviewDetail,
    RequirementReviewCaseReviewWrite,
    RequirementReviewDecision,
    RequirementReviewExtractionSnapshot,
    RequirementReviewIssueCode,
)
from app.db.models import (
    JobORM,
    JobRequirementExtractionORM,
    JobRequirementORM,
    RequirementReviewBatchCaseORM,
    RequirementReviewBatchFinalDecisionORM,
    RequirementReviewBatchORM,
    RequirementReviewCaseReviewORM,
    TraceSpanORM,
)
from app.domain.job_requirements import RequirementImportance, RequirementType

SessionFactory = Callable[[], Session]
FORMAL_REVIEW_SAMPLE_SIZE = 20


class SqlAlchemyRequirementReviewRepository(AbstractRequirementReviewRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def add_batch(self, batch: RequirementReviewBatchWrite) -> None:
        record = RequirementReviewBatchORM(
            id=batch.batch_id,
            title=batch.title,
            reviewer=batch.reviewer,
            provider=batch.provider,
            model=batch.model,
            extractor_version=batch.extractor_version,
            prompt_version=batch.prompt_version,
            sample_size=len(batch.cases),
        )
        record.cases.extend(
            RequirementReviewBatchCaseORM(
                id=item.case_id,
                case_index=item.case_index,
                job_id=item.job_id,
                extraction_id=item.extraction_id,
            )
            for item in batch.cases
        )
        self._session.add(record)
        self._session.flush()

    def add_case_review(self, review: RequirementReviewCaseReviewWrite) -> None:
        self._session.add(
            RequirementReviewCaseReviewORM(
                id=review.review_id,
                batch_case_id=review.batch_case_id,
                decision=review.decision.value,
                issue_codes=[item.value for item in review.issue_codes],
                notes=review.notes,
                reviewed_at=review.reviewed_at,
            )
        )
        try:
            self._session.flush()
        except IntegrityError as error:
            message = str(error.orig).casefold()
            if (
                "requirement_review_case_reviews.batch_case_id" in message
                or "uq_requirement_review_case_reviews_case" in message
            ):
                raise RequirementReviewCaseAlreadyReviewedError(
                    f"Requirement Review Case {review.batch_case_id!r} already has an immutable review"
                ) from error
            raise

    def add_final_decision(
        self,
        decision: RequirementReviewBatchFinalDecisionWrite,
    ) -> None:
        self._session.add(
            RequirementReviewBatchFinalDecisionORM(
                id=decision.decision_id,
                batch_id=decision.batch_id,
                decision=decision.decision.value,
                reviewer=decision.reviewer,
                notes=decision.notes,
                sample_size=decision.sample_size,
                reviewed_count=decision.reviewed_count,
                accepted_count=decision.accepted_count,
                rejected_count=decision.rejected_count,
                stale_case_count=decision.stale_case_count,
                issue_code_counts=dict(decision.issue_code_counts),
                evidence_fingerprint=decision.evidence_fingerprint,
                decided_at=decision.decided_at,
            )
        )
        try:
            self._session.flush()
        except IntegrityError as error:
            message = str(error.orig).casefold()
            if (
                "requirement_review_batch_final_decisions.batch_id" in message
                or "uq_requirement_review_batch_final_decisions_batch" in message
            ):
                raise RequirementReviewBatchFinalDecisionAlreadyExistsError(
                    f"Requirement Review Batch {decision.batch_id!r} already has an immutable final decision"
                ) from error
            raise


class SqlAlchemyRequirementReviewQueryRepository(
    AbstractRequirementReviewQueryRepository
):
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def list_candidates(self, *, limit: int, offset: int) -> RequirementReviewCandidatePage:
        with self._session_factory() as session:
            latest = _latest_extractions(session)
            jobs = _jobs_by_id(session, set(latest))
            ordered = sorted(
                (
                    item
                    for item in latest.values()
                    if _matches_current_job_input(item, jobs[item.job_id])
                ),
                key=lambda item: (_utc(item.created_at), item.id),
                reverse=True,
            )
            selected = ordered[offset : offset + limit]
            return RequirementReviewCandidatePage(
                total=len(ordered),
                limit=limit,
                offset=offset,
                items=tuple(
                    RequirementReviewCandidate(
                        extraction_id=item.id,
                        job_id=item.job_id,
                        title=jobs[item.job_id].title,
                        company=jobs[item.job_id].company,
                        provider=item.provider,
                        model=item.model,
                        extractor_version=item.extractor_version,
                        prompt_version=item.prompt_version,
                        trace_run_id=item.trace_run_id,
                        requirement_count=item.requirement_count,
                        created_at=_utc(item.created_at),
                        semantic_policy_version=_semantic_policy_version(
                            session, item.trace_run_id
                        ),
                    )
                    for item in selected
                ),
            )

    def get_extraction_snapshots(
        self,
        extraction_ids: tuple[str, ...],
    ) -> tuple[RequirementReviewExtractionSnapshot, ...]:
        if not extraction_ids:
            return ()
        with self._session_factory() as session:
            rows = session.execute(
                select(JobRequirementExtractionORM, JobORM)
                .join(JobORM, JobORM.id == JobRequirementExtractionORM.job_id)
                .where(JobRequirementExtractionORM.id.in_(extraction_ids))
            ).all()
            latest = _latest_extractions(
                session,
                {record.job_id for record, _job in rows},
            )
            return tuple(
                RequirementReviewExtractionSnapshot(
                    extraction_id=record.id,
                    job_id=record.job_id,
                    title=job.title,
                    company=job.company,
                    description=job.description,
                    provider=record.provider,
                    model=record.model,
                    extractor_version=record.extractor_version,
                    prompt_version=record.prompt_version,
                    trace_run_id=record.trace_run_id,
                    requirement_count=record.requirement_count,
                    created_at=_utc(record.created_at),
                    is_current=(
                        latest.get(record.job_id) is not None
                        and latest[record.job_id].id == record.id
                        and _matches_current_job_input(record, job)
                    ),
                    semantic_policy_version=_semantic_policy_version(
                        session, record.trace_run_id
                    ),
                )
                for record, job in rows
            )

    def list_batches(self, *, limit: int, offset: int) -> RequirementReviewBatchPage:
        with self._session_factory() as session:
            total = int(
                session.scalar(select(func.count()).select_from(RequirementReviewBatchORM))
                or 0
            )
            records = session.scalars(
                select(RequirementReviewBatchORM)
                .order_by(
                    RequirementReviewBatchORM.created_at.desc(),
                    RequirementReviewBatchORM.id.asc(),
                )
                .limit(limit)
                .offset(offset)
            ).all()
            return RequirementReviewBatchPage(
                total=total,
                limit=limit,
                offset=offset,
                items=tuple(_batch_detail(session, item).summary for item in records),
            )

    def get_batch(self, batch_id: str) -> RequirementReviewBatchDetail | None:
        with self._session_factory() as session:
            record = session.get(RequirementReviewBatchORM, batch_id)
            return _batch_detail(session, record) if record is not None else None

    def get_case(
        self,
        *,
        batch_id: str,
        case_id: str,
    ) -> RequirementReviewBatchCaseLookup | None:
        with self._session_factory() as session:
            record = session.scalar(
                select(RequirementReviewBatchCaseORM).where(
                    RequirementReviewBatchCaseORM.id == case_id,
                    RequirementReviewBatchCaseORM.batch_id == batch_id,
                )
            )
            if record is None:
                return None
            review = session.scalar(
                select(RequirementReviewCaseReviewORM).where(
                    RequirementReviewCaseReviewORM.batch_case_id == case_id
                )
            )
            return RequirementReviewBatchCaseLookup(
                batch_id=batch_id,
                batch_case_id=case_id,
                review=_review_detail(review) if review is not None else None,
            )

    def get_case_review(self, case_id: str) -> RequirementReviewCaseReviewDetail | None:
        with self._session_factory() as session:
            record = session.scalar(
                select(RequirementReviewCaseReviewORM).where(
                    RequirementReviewCaseReviewORM.batch_case_id == case_id
                )
            )
            return _review_detail(record) if record is not None else None

    def get_final_decision(
        self,
        batch_id: str,
    ) -> RequirementReviewBatchFinalDecisionDetail | None:
        with self._session_factory() as session:
            record = session.scalar(
                select(RequirementReviewBatchFinalDecisionORM).where(
                    RequirementReviewBatchFinalDecisionORM.batch_id == batch_id
                )
            )
            return _final_decision_detail(record) if record is not None else None

    def get_accepted_baseline(self) -> AcceptedRequirementReviewBaseline | None:
        with self._session_factory() as session:
            decisions = session.scalars(
                select(RequirementReviewBatchFinalDecisionORM)
                .where(
                    RequirementReviewBatchFinalDecisionORM.decision
                    == RequirementReviewBatchFinalDecision.ACCEPT_FOR_MATCH.value
                )
                .order_by(
                    RequirementReviewBatchFinalDecisionORM.decided_at.desc(),
                    RequirementReviewBatchFinalDecisionORM.id.desc(),
                )
            ).all()
            for record in decisions:
                batch = session.get(RequirementReviewBatchORM, record.batch_id)
                if batch is None:
                    continue
                detail = _batch_detail(session, batch)
                if detail.summary.match_release_eligible:
                    return AcceptedRequirementReviewBaseline(
                        decision=_final_decision_detail(record),
                        batch=detail.summary,
                        issue_code_counts=dict(detail.issue_code_counts),
                    )
            return None


def _latest_extractions(
    session: Session,
    job_ids: set[str] | None = None,
) -> dict[str, JobRequirementExtractionORM]:
    statement = select(JobRequirementExtractionORM)
    if job_ids is not None:
        if not job_ids:
            return {}
        statement = statement.where(JobRequirementExtractionORM.job_id.in_(job_ids))
    records = session.scalars(
        statement.order_by(
            JobRequirementExtractionORM.job_id.asc(),
            JobRequirementExtractionORM.created_at.desc(),
            JobRequirementExtractionORM.id.asc(),
        )
    ).all()
    latest: dict[str, JobRequirementExtractionORM] = {}
    for record in records:
        latest.setdefault(record.job_id, record)
    return latest


def _matches_current_job_input(
    extraction: JobRequirementExtractionORM,
    job: JobORM,
) -> bool:
    description = (job.description or "").strip()
    return extraction.input_hash == sha256(description.encode("utf-8")).hexdigest()


def _jobs_by_id(session: Session, job_ids: set[str]) -> dict[str, JobORM]:
    if not job_ids:
        return {}
    return {
        item.id: item
        for item in session.scalars(select(JobORM).where(JobORM.id.in_(job_ids))).all()
    }


def _batch_detail(
    session: Session,
    batch: RequirementReviewBatchORM,
) -> RequirementReviewBatchDetail:
    rows = session.execute(
        select(
            RequirementReviewBatchCaseORM,
            JobORM,
            JobRequirementExtractionORM,
            RequirementReviewCaseReviewORM,
        )
        .join(JobORM, JobORM.id == RequirementReviewBatchCaseORM.job_id)
        .join(
            JobRequirementExtractionORM,
            JobRequirementExtractionORM.id
            == RequirementReviewBatchCaseORM.extraction_id,
        )
        .outerjoin(
            RequirementReviewCaseReviewORM,
            RequirementReviewCaseReviewORM.batch_case_id
            == RequirementReviewBatchCaseORM.id,
        )
        .where(RequirementReviewBatchCaseORM.batch_id == batch.id)
        .order_by(RequirementReviewBatchCaseORM.case_index.asc())
    ).all()
    extraction_ids = {extraction.id for _case, _job, extraction, _review in rows}
    job_ids = {case.job_id for case, _job, _extraction, _review in rows}
    latest = _latest_extractions(session, job_ids)
    requirements_by_extraction: dict[str, list[JobRequirementDetail]] = defaultdict(list)
    if extraction_ids:
        requirements = session.scalars(
            select(JobRequirementORM)
            .where(JobRequirementORM.extraction_id.in_(extraction_ids))
            .order_by(
                JobRequirementORM.extraction_id.asc(),
                JobRequirementORM.requirement_index.asc(),
            )
        ).all()
        for item in requirements:
            requirements_by_extraction[item.extraction_id].append(
                JobRequirementDetail(
                    id=item.id,
                    job_id=item.job_id,
                    extraction_id=item.extraction_id,
                    requirement_index=item.requirement_index,
                    type=RequirementType(item.type),
                    original_text=item.original_text,
                    normalized_capability=item.normalized_capability,
                    importance=RequirementImportance(item.importance),
                    evidence_span=item.evidence_span,
                    confidence=item.confidence,
                    extractor_version=item.extractor_version,
                )
            )

    case_details: list[RequirementReviewBatchCaseDetail] = []
    issue_counts: dict[str, int] = defaultdict(int)
    accepted_count = 0
    rejected_count = 0
    stale_count = 0
    for case, job, extraction, review_record in rows:
        review = _review_detail(review_record) if review_record is not None else None
        if review is not None:
            if review.decision is RequirementReviewDecision.ACCEPTED:
                accepted_count += 1
            else:
                rejected_count += 1
            for issue in review.issue_codes:
                issue_counts[issue.value] += 1
        is_current = (
            latest.get(case.job_id) is not None
            and latest[case.job_id].id == extraction.id
            and _matches_current_job_input(extraction, job)
        )
        if not is_current:
            stale_count += 1
        case_details.append(
            RequirementReviewBatchCaseDetail(
                id=case.id,
                case_index=case.case_index,
                job_id=case.job_id,
                extraction_id=case.extraction_id,
                title=job.title,
                company=job.company,
                description=job.description,
                provider=extraction.provider,
                model=extraction.model,
                extractor_version=extraction.extractor_version,
                prompt_version=extraction.prompt_version,
                trace_run_id=extraction.trace_run_id,
                created_at=_utc(extraction.created_at),
                is_current=is_current,
                requirements=tuple(requirements_by_extraction[extraction.id]),
                review=review,
                semantic_policy_version=_semantic_policy_version(
                    session, extraction.trace_run_id
                ),
            )
        )

    reviewed_count = accepted_count + rejected_count
    completed = reviewed_count == batch.sample_size
    semantic_policy_version = _single_semantic_policy_version(case_details)
    formal_evidence_eligible = (
        batch.sample_size == FORMAL_REVIEW_SAMPLE_SIZE
        and completed
        and stale_count == 0
        and batch.provider.casefold() != "fixture"
        and semantic_policy_version is not None
    )
    final_record = session.scalar(
        select(RequirementReviewBatchFinalDecisionORM).where(
            RequirementReviewBatchFinalDecisionORM.batch_id == batch.id
        )
    )
    final_decision = (
        _final_decision_detail(final_record) if final_record is not None else None
    )
    match_release_eligible = (
        formal_evidence_eligible
        and final_decision is not None
        and final_decision.decision
        is RequirementReviewBatchFinalDecision.ACCEPT_FOR_MATCH
    )
    return RequirementReviewBatchDetail(
        summary=RequirementReviewBatchSummary(
            id=batch.id,
            title=batch.title,
            reviewer=batch.reviewer,
            provider=batch.provider,
            model=batch.model,
            extractor_version=batch.extractor_version,
            prompt_version=batch.prompt_version,
            sample_size=batch.sample_size,
            reviewed_count=reviewed_count,
            accepted_count=accepted_count,
            rejected_count=rejected_count,
            stale_case_count=stale_count,
            completed=completed,
            formal_evidence_eligible=formal_evidence_eligible,
            final_decision=(
                final_decision.decision if final_decision is not None else None
            ),
            match_release_eligible=match_release_eligible,
            created_at=_utc(batch.created_at),
            semantic_policy_version=semantic_policy_version,
        ),
        issue_code_counts=dict(sorted(issue_counts.items())),
        cases=tuple(case_details),
        final_decision=final_decision,
    )


def _semantic_policy_version(session: Session, trace_run_id: str) -> str | None:
    trace = session.get(TraceSpanORM, trace_run_id)
    if trace is None or not isinstance(trace.output, dict):
        return None
    value = trace.output.get("semanticPolicyVersion")
    return value.strip() if isinstance(value, str) and value.strip() else None


def _single_semantic_policy_version(
    cases: list[RequirementReviewBatchCaseDetail],
) -> str | None:
    versions = {case.semantic_policy_version for case in cases}
    return next(iter(versions)) if len(versions) == 1 else None


def _final_decision_detail(
    record: RequirementReviewBatchFinalDecisionORM,
) -> RequirementReviewBatchFinalDecisionDetail:
    return RequirementReviewBatchFinalDecisionDetail(
        id=record.id,
        batch_id=record.batch_id,
        decision=RequirementReviewBatchFinalDecision(record.decision),
        reviewer=record.reviewer,
        notes=record.notes,
        sample_size=record.sample_size,
        reviewed_count=record.reviewed_count,
        accepted_count=record.accepted_count,
        rejected_count=record.rejected_count,
        stale_case_count=record.stale_case_count,
        issue_code_counts=dict(record.issue_code_counts),
        evidence_fingerprint=record.evidence_fingerprint,
        decided_at=_utc(record.decided_at),
    )


def _review_detail(
    record: RequirementReviewCaseReviewORM,
) -> RequirementReviewCaseReviewDetail:
    return RequirementReviewCaseReviewDetail(
        id=record.id,
        batch_case_id=record.batch_case_id,
        decision=RequirementReviewDecision(record.decision),
        issue_codes=tuple(RequirementReviewIssueCode(item) for item in record.issue_codes),
        notes=record.notes,
        reviewed_at=_utc(record.reviewed_at),
    )


def _utc(value):
    return (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )

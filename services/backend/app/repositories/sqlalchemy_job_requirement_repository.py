"""SQLAlchemy persistence for immutable Job Requirement Extraction Runs."""
from __future__ import annotations

from collections.abc import Callable
from datetime import timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.job_requirements import (
    JobRequirementDetail,
    JobRequirementExtractionDetail,
    JobRequirementExtractionWrite,
)
from app.application.ports.job_requirement_repository import (
    AbstractJobRequirementQueryRepository,
    AbstractJobRequirementRepository,
)
from app.db.models import JobRequirementExtractionORM, JobRequirementORM, TraceSpanORM
from app.domain.job_requirements import RequirementImportance, RequirementType

SessionFactory = Callable[[], Session]


class SqlAlchemyJobRequirementRepository(AbstractJobRequirementRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, extraction: JobRequirementExtractionWrite) -> None:
        record = JobRequirementExtractionORM(
            id=extraction.extraction_id,
            job_id=extraction.job_id,
            input_hash=extraction.input_hash,
            description_characters=extraction.description_characters,
            extractor_version=extraction.extractor_version,
            provider=extraction.provider,
            model=extraction.model,
            prompt_version=extraction.prompt_version,
            trace_run_id=extraction.trace_run_id,
            requirement_count=len(extraction.requirements),
        )
        record.requirements.extend(
            JobRequirementORM(
                id=item.requirement_id,
                job_id=item.job_id,
                requirement_index=item.requirement_index,
                type=item.type.value,
                original_text=item.original_text,
                normalized_capability=item.normalized_capability,
                importance=item.importance.value,
                evidence_span=item.evidence_span,
                confidence=item.confidence,
                extractor_version=item.extractor_version,
            )
            for item in extraction.requirements
        )
        self._session.add(record)
        self._session.flush()


class SqlAlchemyJobRequirementQueryRepository(
    AbstractJobRequirementQueryRepository
):
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def get_latest(self, job_id: str) -> JobRequirementExtractionDetail | None:
        with self._session_factory() as session:
            record = session.scalar(
                select(JobRequirementExtractionORM)
                .where(JobRequirementExtractionORM.job_id == job_id)
                .order_by(
                    JobRequirementExtractionORM.created_at.desc(),
                    JobRequirementExtractionORM.id.asc(),
                )
                .limit(1)
            )
            return _detail(session, record) if record is not None else None

    def get_extraction(
        self,
        *,
        job_id: str,
        extraction_id: str,
    ) -> JobRequirementExtractionDetail | None:
        with self._session_factory() as session:
            record = session.scalar(
                select(JobRequirementExtractionORM).where(
                    JobRequirementExtractionORM.id == extraction_id,
                    JobRequirementExtractionORM.job_id == job_id,
                )
            )
            return _detail(session, record) if record is not None else None


def _detail(
    session: Session,
    record: JobRequirementExtractionORM,
) -> JobRequirementExtractionDetail:
    requirements = session.scalars(
        select(JobRequirementORM)
        .where(JobRequirementORM.extraction_id == record.id)
        .order_by(JobRequirementORM.requirement_index.asc())
    ).all()
    created_at = (
        record.created_at.replace(tzinfo=timezone.utc)
        if record.created_at.tzinfo is None
        else record.created_at.astimezone(timezone.utc)
    )
    trace = session.get(TraceSpanORM, record.trace_run_id)
    semantic_policy_version = None
    if trace is not None and isinstance(trace.output, dict):
        raw_semantic_policy_version = trace.output.get("semanticPolicyVersion")
        if isinstance(raw_semantic_policy_version, str) and raw_semantic_policy_version.strip():
            semantic_policy_version = raw_semantic_policy_version.strip()

    return JobRequirementExtractionDetail(
        extraction_id=record.id,
        job_id=record.job_id,
        input_hash=record.input_hash,
        extractor_version=record.extractor_version,
        provider=record.provider,
        model=record.model,
        prompt_version=record.prompt_version,
        trace_run_id=record.trace_run_id,
        requirement_count=record.requirement_count,
        created_at=created_at,
        requirements=tuple(
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
            for item in requirements
        ),
        semantic_policy_version=semantic_policy_version,
    )

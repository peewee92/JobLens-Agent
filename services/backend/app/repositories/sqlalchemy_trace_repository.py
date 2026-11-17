"""SQLAlchemy trace persistence adapter."""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy

from sqlalchemy import func, select, tuple_
from sqlalchemy.orm import Session

from app.application.ports.trace_repository import AbstractTraceRepository
from app.application.tracing import TraceWrite
from app.db.models import TraceSpanORM


class SqlAlchemyTraceRepository(AbstractTraceRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, trace: TraceWrite) -> None:
        self._session.add(
            TraceSpanORM(
                id=trace.run_id,
                capability=trace.capability,
                version=trace.version,
                model=trace.model,
                prompt_version=trace.prompt_version,
                input_refs=deepcopy(trace.input_refs),
                output=deepcopy(trace.output),
                latency_ms=trace.latency_ms,
                input_tokens=trace.input_tokens,
                output_tokens=trace.output_tokens,
                error=trace.error,
            )
        )
        self._session.flush()

    def failed_offline_requirement_jobs(self, descriptions: Mapping[str, str]) -> set[str]:
        """Read the latest attempt for each exact job/description, without returning trace content."""
        if not descriptions:
            return set()
        job_id = TraceSpanORM.input_refs["jobId"].as_string()
        description_hash = TraceSpanORM.input_refs["descriptionSha256"].as_string()
        attempts = (
            select(
                job_id.label("job_id"),
                (TraceSpanORM.model.in_(("fixture-requirement-extractor", "fixture-requirement-extractor-v2"))
                 & TraceSpanORM.error.is_not(None)
                 & (TraceSpanORM.input_refs["providerCalls"].as_integer() == 0)).label("failed_offline"),
                func.row_number().over(
                    partition_by=(job_id, description_hash),
                    order_by=(TraceSpanORM.created_at.desc(), TraceSpanORM.id.desc()),
                ).label("position"),
            )
            .where(
                TraceSpanORM.capability == "requirement_extraction",
                tuple_(job_id, description_hash).in_(descriptions.items()),
            )
            .subquery()
        )
        return set(self._session.scalars(
            select(attempts.c.job_id).where(attempts.c.position == 1, attempts.c.failed_offline)
        ))

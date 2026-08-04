"""SQLAlchemy adapter for Requirement release Trace facts."""
from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session

from app.application.ports.job_requirement_release_repository import (
    AbstractJobRequirementReleaseQueryRepository,
    JobRequirementTraceFact,
)
from app.db.models import TraceSpanORM

SessionFactory = Callable[[], Session]


class SqlAlchemyJobRequirementReleaseQueryRepository(
    AbstractJobRequirementReleaseQueryRepository
):
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def get_trace(self, trace_run_id: str) -> JobRequirementTraceFact | None:
        with self._session_factory() as session:
            record = session.get(TraceSpanORM, trace_run_id)
            if record is None:
                return None
            return JobRequirementTraceFact(
                trace_run_id=record.id,
                capability=record.capability,
                version=record.version,
                model=record.model,
                prompt_version=record.prompt_version,
                input_refs=dict(record.input_refs),
                output=(dict(record.output) if record.output is not None else None),
                error=record.error,
            )

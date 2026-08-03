"""SQLAlchemy trace persistence adapter."""
from __future__ import annotations

from copy import deepcopy

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

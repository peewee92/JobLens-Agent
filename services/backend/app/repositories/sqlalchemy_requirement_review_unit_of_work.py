"""SQLAlchemy transaction boundary for Requirement manual review writes."""
from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import RequirementReviewBatchORM, TraceSpanORM

from app.application.ports.requirement_review_unit_of_work import (
    AbstractRequirementReviewUnitOfWork,
)
from app.repositories.sqlalchemy_requirement_review_repository import (
    SqlAlchemyRequirementReviewRepository,
    _batch_detail,
)

SessionFactory = Callable[[], Session]


class SqlAlchemyRequirementReviewUnitOfWork(AbstractRequirementReviewUnitOfWork):
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None

    def __enter__(self) -> "SqlAlchemyRequirementReviewUnitOfWork":
        if self._session is not None:
            raise RuntimeError("Requirement Review Unit of Work is already active")
        self._session = self._session_factory()
        self.reviews = SqlAlchemyRequirementReviewRepository(self._session)
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self._session is None:
            return
        try:
            if exc_type is not None:
                self._session.rollback()
            elif self._session.in_transaction():
                self._session.rollback()
        finally:
            self._session.close()
            self._session = None

    def load_batch_for_final_decision(self, batch_id: str):
        session = self._active_session()
        session.connection().exec_driver_sql("BEGIN IMMEDIATE")
        batch = session.get(RequirementReviewBatchORM, batch_id)
        return _batch_detail(session, batch) if batch is not None else None

    def load_evidence_traces(self, trace_ids: tuple[str, ...]) -> dict:
        rows = self._active_session().scalars(select(TraceSpanORM).where(TraceSpanORM.id.in_(trace_ids))).all()
        return {row.id: {"capability": row.capability, "version": row.version,
            "model": row.model, "promptVersion": row.prompt_version,
            "inputRefs": row.input_refs, "output": row.output, "error": row.error,
            "createdAt": row.created_at.isoformat()} for row in rows}

    def commit(self) -> None:
        self._active_session().commit()

    def rollback(self) -> None:
        self._active_session().rollback()

    def _active_session(self) -> Session:
        if self._session is None:
            raise RuntimeError("Requirement Review Unit of Work is not active")
        return self._session

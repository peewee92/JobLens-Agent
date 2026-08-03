"""SQLAlchemy transaction boundary for capability traces."""
from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session

from app.application.ports.trace_unit_of_work import AbstractTraceUnitOfWork
from app.repositories.sqlalchemy_trace_repository import SqlAlchemyTraceRepository

SessionFactory = Callable[[], Session]


class SqlAlchemyTraceUnitOfWork(AbstractTraceUnitOfWork):
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None

    def __enter__(self) -> "SqlAlchemyTraceUnitOfWork":
        if self._session is not None:
            raise RuntimeError("Trace Unit of Work is already active")
        self._session = self._session_factory()
        self.traces = SqlAlchemyTraceRepository(self._session)
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

    def commit(self) -> None:
        self._active_session().commit()

    def rollback(self) -> None:
        self._active_session().rollback()

    def _active_session(self) -> Session:
        if self._session is None:
            raise RuntimeError("Trace Unit of Work is not active")
        return self._session

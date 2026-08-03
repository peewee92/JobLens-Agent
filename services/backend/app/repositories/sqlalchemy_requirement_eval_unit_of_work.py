"""SQLAlchemy transaction boundary for Requirement Eval runs."""
from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session

from app.application.ports.requirement_eval_unit_of_work import (
    AbstractRequirementEvalUnitOfWork,
)
from app.repositories.sqlalchemy_requirement_eval_repository import (
    SqlAlchemyRequirementEvalRepository,
)

SessionFactory = Callable[[], Session]


class SqlAlchemyRequirementEvalUnitOfWork(AbstractRequirementEvalUnitOfWork):
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None

    def __enter__(self) -> "SqlAlchemyRequirementEvalUnitOfWork":
        if self._session is not None:
            raise RuntimeError("Requirement Eval Unit of Work is already active")
        self._session = self._session_factory()
        self.eval_runs = SqlAlchemyRequirementEvalRepository(self._session)
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
            raise RuntimeError("Requirement Eval Unit of Work is not active")
        return self._session

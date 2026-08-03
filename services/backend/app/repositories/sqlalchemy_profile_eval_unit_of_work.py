"""SQLAlchemy transaction boundary for Profile Eval runs."""
from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session

from app.application.ports.profile_eval_unit_of_work import AbstractProfileEvalUnitOfWork
from app.repositories.sqlalchemy_profile_eval_repository import SqlAlchemyProfileEvalRepository

SessionFactory = Callable[[], Session]


class SqlAlchemyProfileEvalUnitOfWork(AbstractProfileEvalUnitOfWork):
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None

    def __enter__(self) -> "SqlAlchemyProfileEvalUnitOfWork":
        if self._session is not None:
            raise RuntimeError("Profile Eval Unit of Work is already active")
        self._session = self._session_factory()
        self.eval_runs = SqlAlchemyProfileEvalRepository(self._session)
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
            raise RuntimeError("Profile Eval Unit of Work is not active")
        return self._session

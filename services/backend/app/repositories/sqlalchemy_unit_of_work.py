"""SQLAlchemy Unit of Work implementation for application transactions."""
from __future__ import annotations

from types import TracebackType
from typing import Callable, Self

from sqlalchemy.orm import Session

from app.application.ports.unit_of_work import AbstractUnitOfWork
from app.repositories.sqlalchemy_job_repository import SqlAlchemyJobRepository

SessionFactory = Callable[[], Session]


class SqlAlchemyUnitOfWork(AbstractUnitOfWork):
    """Create one Session and share it across repositories for one use case.

    Commit is explicit. Leaving the context without commit, or leaving because
    of an exception, rolls back any unfinished transaction before closing the
    Session. This prevents partial persistence when a multi-step use case fails.
    """

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None
        self.jobs: SqlAlchemyJobRepository

    def __enter__(self) -> Self:
        if self._session is not None:
            raise RuntimeError("Unit of Work is already active")

        self._session = self._session_factory()
        self.jobs = SqlAlchemyJobRepository(self._session)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        try:
            session = self._require_session()
            if session.in_transaction():
                session.rollback()
        finally:
            self._require_session().close()
            self._session = None

    def commit(self) -> None:
        self._require_session().commit()

    def rollback(self) -> None:
        session = self._require_session()
        if session.in_transaction():
            session.rollback()

    def _require_session(self) -> Session:
        if self._session is None:
            raise RuntimeError("Unit of Work is not active")
        return self._session

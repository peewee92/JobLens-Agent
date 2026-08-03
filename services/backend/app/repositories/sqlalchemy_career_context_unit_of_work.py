"""SQLAlchemy Unit of Work for Profile/SearchIntent commands."""
from __future__ import annotations

from collections.abc import Callable
from types import TracebackType

from sqlalchemy.orm import Session

from app.application.ports.career_context_repository import (
    AbstractCareerContextRepository,
)
from app.application.ports.career_context_unit_of_work import (
    AbstractCareerContextUnitOfWork,
)
from app.repositories.sqlalchemy_career_context_repository import (
    SqlAlchemyCareerContextRepository,
)

SessionFactory = Callable[[], Session]


class SqlAlchemyCareerContextUnitOfWork(AbstractCareerContextUnitOfWork):
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None
        self.context: AbstractCareerContextRepository

    def __enter__(self) -> "SqlAlchemyCareerContextUnitOfWork":
        if self._session is not None:
            raise RuntimeError("CareerContext UnitOfWork is already active")
        self._session = self._session_factory()
        self.context = SqlAlchemyCareerContextRepository(self._session)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        session = self._require_session()
        try:
            if session.in_transaction():
                session.rollback()
        finally:
            session.close()
            self._session = None

    def commit(self) -> None:
        self._require_session().commit()

    def rollback(self) -> None:
        self._require_session().rollback()

    def _require_session(self) -> Session:
        if self._session is None:
            raise RuntimeError("CareerContext UnitOfWork is not active")
        return self._session

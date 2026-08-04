"""SQLAlchemy transaction boundary for Requirement manual review writes."""
from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session

from app.application.ports.requirement_review_unit_of_work import (
    AbstractRequirementReviewUnitOfWork,
)
from app.repositories.sqlalchemy_requirement_review_repository import (
    SqlAlchemyRequirementReviewRepository,
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

    def commit(self) -> None:
        self._active_session().commit()

    def rollback(self) -> None:
        self._active_session().rollback()

    def _active_session(self) -> Session:
        if self._session is None:
            raise RuntimeError("Requirement Review Unit of Work is not active")
        return self._session

"""SQLAlchemy Unit of Work for Job Requirement Extraction persistence."""
from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session

from app.application.ports.job_requirement_unit_of_work import (
    AbstractJobRequirementUnitOfWork,
)
from app.repositories.sqlalchemy_job_requirement_repository import (
    SqlAlchemyJobRequirementRepository,
)

SessionFactory = Callable[[], Session]


class SqlAlchemyJobRequirementUnitOfWork(AbstractJobRequirementUnitOfWork):
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None

    def __enter__(self) -> "SqlAlchemyJobRequirementUnitOfWork":
        self._session = self._session_factory()
        self.requirements = SqlAlchemyJobRequirementRepository(self._session)
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        try:
            if exc_type is not None:
                self.rollback()
        finally:
            if self._session is not None:
                self._session.close()
                self._session = None

    def commit(self) -> None:
        assert self._session is not None
        self._session.commit()

    def rollback(self) -> None:
        if self._session is not None:
            self._session.rollback()

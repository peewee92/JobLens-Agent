"""SQLAlchemy Unit of Work for Job Requirement Extraction persistence."""
from __future__ import annotations

from collections.abc import Callable
from hashlib import sha256

from sqlalchemy import select

from app.db.models import JobORM, JobRequirementExtractionORM
from app.application.job_requirements.errors import JobDescriptionChangedDuringExtractionError, RequirementExtractionSupersededError

from sqlalchemy.orm import Session

from app.repositories.sqlalchemy_job_availability_guard import lock_and_check_job_availability

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

    def ensure_job_availability(self, job_id: str, revision: int) -> None:
        assert self._session is not None
        lock_and_check_job_availability(self._session, job_id, revision)

    def ensure_description_hash(self, job_id: str, input_hash: str) -> None:
        assert self._session is not None
        description = self._session.scalar(select(JobORM.description).where(JobORM.id == job_id))
        current_hash = sha256((description or "").strip().encode("utf-8")).hexdigest()
        if current_hash != input_hash:
            raise JobDescriptionChangedDuringExtractionError(
                "分析期间岗位描述发生变化，结果未保存；请检查岗位后重新分析。"
            )

    def ensure_latest_extraction(self, job_id: str, expected_id: str | None) -> None:
        assert self._session is not None
        latest_id = self._session.scalar(select(JobRequirementExtractionORM.id)
            .where(JobRequirementExtractionORM.job_id == job_id)
            .order_by(JobRequirementExtractionORM.created_at.desc(), JobRequirementExtractionORM.id.asc())
            .limit(1))
        if latest_id != expected_id:
            raise RequirementExtractionSupersededError(
                "另一次岗位要求分析已保存，本次结果未保存；请先查看已有结果。"
            )

    def commit(self) -> None:
        assert self._session is not None
        self._session.commit()

    def rollback(self) -> None:
        if self._session is not None:
            self._session.rollback()

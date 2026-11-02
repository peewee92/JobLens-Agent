"""Short local SQLite transaction: inspect current facts and append confirmation."""
from contextlib import nullcontext
from datetime import UTC
from dataclasses import asdict
from sqlalchemy import text

from app.application.job_requirements.confirmation import RequirementConfirmation, RequirementConfirmationConflict
from app.application.job_requirements.release import GetJobRequirementReleaseReadinessUseCase
from app.db.models import JobRequirementConfirmationORM
from app.repositories.sqlalchemy_job_query_repository import SqlAlchemyJobQueryRepository
from app.repositories.sqlalchemy_job_requirement_repository import SqlAlchemyJobRequirementQueryRepository
from app.repositories.sqlalchemy_job_requirement_release_repository import SqlAlchemyJobRequirementReleaseQueryRepository
from app.repositories.sqlalchemy_requirement_review_repository import SqlAlchemyRequirementReviewQueryRepository


class SqlAlchemyRequirementConfirmationUnitOfWork:
    def __init__(self, session_factory):
        self._factory = session_factory

    def __enter__(self):
        self._session = self._factory()
        try:
            self._session.execute(text("BEGIN IMMEDIATE"))
        except Exception:
            self._session.close()
            raise
        return self

    def __exit__(self, *args):
        try:
            self._session.rollback()
        finally:
            self._session.close()

    def get(self, action_id):
        row = self._session.get(JobRequirementConfirmationORM, action_id)
        if row is None:
            return None
        return RequirementConfirmation(row.action_id, row.job_id, row.extraction_id, row.input_hash,
            row.facts_digest, row.confirmed_at.replace(tzinfo=UTC) if row.confirmed_at.tzinfo is None else row.confirmed_at)

    def inspect(self, job_id):
        borrowed = lambda: nullcontext(self._session)
        jobs = SqlAlchemyJobQueryRepository(borrowed)
        job = jobs.get_job(job_id)
        if job is not None and job.user_marked_inactive:
            raise RequirementConfirmationConflict("job_user_marked_inactive")
        return GetJobRequirementReleaseReadinessUseCase(
            jobs=jobs, requirements=SqlAlchemyJobRequirementQueryRepository(borrowed),
            reviews=SqlAlchemyRequirementReviewQueryRepository(borrowed),
            traces=SqlAlchemyJobRequirementReleaseQueryRepository(borrowed),
        ).inspect_facts(job_id)

    def add(self, record):
        self._session.add(JobRequirementConfirmationORM(**asdict(record)))
        self._session.flush()

    def commit(self):
        self._session.commit()

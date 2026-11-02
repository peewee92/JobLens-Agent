"""User availability is a single conditional write, separate from source imports."""
from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from app.application.job_queries.errors import JobAvailabilityPersistenceError
from app.db.models import JobORM


class SqlAlchemyJobAvailability:
    def __init__(self, factory):
        self._factory = factory

    def set(self, job_id: str, *, inactive: bool, expected_revision: int):
        try:
            return self._set(job_id, inactive=inactive, expected_revision=expected_revision)
        except SQLAlchemyError as exc:
            raise JobAvailabilityPersistenceError() from exc

    def _set(self, job_id: str, *, inactive: bool, expected_revision: int):
        with self._factory() as session:
            # A repeated request for a state already present does not create a revision.
            result = session.execute(update(JobORM).where(
                JobORM.id == job_id,
                JobORM.availability_revision == expected_revision,
                JobORM.user_marked_inactive != inactive,
            ).values(user_marked_inactive=inactive,
                     availability_revision=JobORM.availability_revision + 1))
            row = session.execute(select(JobORM.user_marked_inactive, JobORM.availability_revision)
                                  .where(JobORM.id == job_id)).one_or_none()
            if row is None:
                session.rollback()
                return None
            # Accept a replay of the immediately preceding identical state change.
            if not result.rowcount and not (row.user_marked_inactive == inactive and
                    row.availability_revision in (expected_revision, expected_revision + 1)):
                session.rollback()
                return False
            session.commit()
            return {"jobId": job_id, "userMarkedInactive": row.user_marked_inactive,
                    "availabilityRevision": row.availability_revision}

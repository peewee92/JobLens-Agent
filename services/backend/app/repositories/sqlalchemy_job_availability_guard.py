"""Serialize an availability check with a short SQLite write transaction."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.job_availability_guard import JobUnavailableForMatchingError
from app.db.models import JobORM


def lock_and_check_job_availability(session: Session, job_id: str, revision: int) -> None:
    # This is the first statement in the unit of work. External work must already
    # have finished; no provider call is performed while holding the writer lock.
    session.connection().exec_driver_sql("BEGIN IMMEDIATE")
    row = session.execute(
        select(JobORM.user_marked_inactive, JobORM.availability_revision)
        .where(JobORM.id == job_id)
    ).one_or_none()
    if row is None or row.user_marked_inactive or row.availability_revision != revision:
        raise JobUnavailableForMatchingError(
            "分析期间岗位有效性发生变化，请检查岗位状态后重新分析。",
            code="job_availability_changed",
        )

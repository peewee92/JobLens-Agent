"""SQLAlchemy implementation of the Job Pool query port."""
from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import case, exists, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.application.job_queries.models import (
    JobDetail,
    JobListItem,
    JobListQuery,
    JobPage,
    JobSort,
)
from app.application.ports.job_query_repository import AbstractJobQueryRepository
from app.db.models import JobORM, JobSourceORM

SessionFactory = Callable[[], Session]


def _literal_contains(value: str) -> str:
    """Build a LIKE pattern while treating user %, _ and backslash literally."""

    escaped = value.casefold().replace("\\", "\\\\")
    escaped = escaped.replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _source_quality(
    source_raw: dict | None,
) -> tuple[str | None, bool | None, tuple[str, ...]]:
    raw = source_raw or {}
    quality = raw.get("descriptionQuality")
    eligible = raw.get("requirementReviewEligible")
    reasons_raw = raw.get("requirementReviewIneligibilityReasons") or []
    reasons = tuple(str(item) for item in reasons_raw if str(item).strip())
    return (
        str(quality) if quality is not None else None,
        eligible if isinstance(eligible, bool) else None,
        reasons,
    )


class SqlAlchemyJobQueryRepository(AbstractJobQueryRepository):
    """Execute stable, read-only Job Pool queries using short-lived Sessions."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def fetch_page(self, query: JobListQuery) -> JobPage:
        with self._session_factory() as session:
            filters = self._job_filters(query)
            total = int(
                session.scalar(
                    select(func.count(JobORM.id)).where(*filters)
                )
                or 0
            )

            primary_source = aliased(JobSourceORM)
            primary_source_id = self._primary_source_id(query.source)
            statement = (
                select(
                    JobORM.id,
                    JobORM.title,
                    JobORM.company,
                    JobORM.area,
                    JobORM.salary_min_k,
                    JobORM.salary_max_k,
                    JobORM.remote_status,
                    JobORM.remote_confidence,
                    primary_source.source,
                    primary_source.source_url,
                    primary_source.source_version,
                    primary_source.collected_at,
                )
                .join(primary_source, primary_source.id == primary_source_id)
                .where(*filters)
                .order_by(*self._order_by(query.sort, primary_source))
                .limit(query.limit)
                .offset(query.offset)
            )
            rows = session.execute(statement).all()

        items = tuple(
            JobListItem(
                id=row.id,
                title=row.title,
                company=row.company,
                area=row.area,
                salary_min_k=row.salary_min_k,
                salary_max_k=row.salary_max_k,
                remote_status=row.remote_status,
                remote_confidence=row.remote_confidence,
                source=row.source,
                source_url=row.source_url,
                source_version=row.source_version,
                collected_at=_as_utc(row.collected_at),
            )
            for row in rows
        )
        return JobPage(
            total=total,
            limit=query.limit,
            offset=query.offset,
            items=items,
        )

    def get_job(self, job_id: str) -> JobDetail | None:
        with self._session_factory() as session:
            primary_source = aliased(JobSourceORM)
            statement = (
                select(
                    JobORM.id,
                    JobORM.title,
                    JobORM.company,
                    JobORM.area,
                    JobORM.salary_min_k,
                    JobORM.salary_max_k,
                    JobORM.experience,
                    JobORM.education,
                    JobORM.description,
                    JobORM.skills,
                    JobORM.remote_status,
                    JobORM.remote_confidence,
                    primary_source.source,
                    primary_source.source_url,
                    primary_source.source_version,
                    primary_source.source_raw,
                    primary_source.collected_at,
                )
                .join(primary_source, primary_source.id == self._primary_source_id())
                .where(JobORM.id == job_id)
            )
            row = session.execute(statement).one_or_none()

        if row is None:
            return None
        description_quality, requirement_review_eligible, ineligibility_reasons = (
            _source_quality(row.source_raw)
        )
        return JobDetail(
            id=row.id,
            title=row.title,
            company=row.company,
            area=row.area,
            salary_min_k=row.salary_min_k,
            salary_max_k=row.salary_max_k,
            experience=row.experience,
            education=row.education,
            description=row.description,
            skills=tuple(row.skills),
            remote_status=row.remote_status,
            remote_confidence=row.remote_confidence,
            source=row.source,
            source_url=row.source_url,
            source_version=row.source_version,
            description_quality=description_quality,
            requirement_review_eligible=requirement_review_eligible,
            requirement_review_ineligibility_reasons=ineligibility_reasons,
            collected_at=_as_utc(row.collected_at),
        )

    @staticmethod
    def _primary_source_id(source: str | None = None):
        candidate = aliased(JobSourceORM)
        statement = select(candidate.id).where(candidate.job_id == JobORM.id)
        if source:
            statement = statement.where(candidate.source == source.casefold())
        return (
            statement.order_by(candidate.last_seen_at.desc(), candidate.id.asc())
            .limit(1)
            .correlate(JobORM)
            .scalar_subquery()
        )

    @staticmethod
    def _job_filters(query: JobListQuery) -> tuple:
        filters: list = []
        if query.q and query.q.strip():
            pattern = _literal_contains(query.q.strip())
            filters.append(
                or_(
                    func.lower(JobORM.title).like(pattern, escape="\\"),
                    func.lower(JobORM.company).like(pattern, escape="\\"),
                    func.lower(JobORM.description).like(pattern, escape="\\"),
                )
            )
        if query.city and query.city.strip():
            filters.append(
                func.lower(JobORM.area).like(
                    _literal_contains(query.city.strip()), escape="\\"
                )
            )
        if query.min_salary_k is not None:
            filters.extend(
                (
                    JobORM.salary_max_k.is_not(None),
                    JobORM.salary_max_k >= query.min_salary_k,
                )
            )
        if query.remote_status is not None:
            filters.append(JobORM.remote_status == query.remote_status)
        source_conditions = [JobSourceORM.job_id == JobORM.id]
        if query.source and query.source.strip():
            source_conditions.append(
                JobSourceORM.source == query.source.strip().casefold()
            )
        filters.append(
            exists(select(JobSourceORM.id).where(*source_conditions))
        )
        return tuple(filters)

    @staticmethod
    def _order_by(sort: JobSort, primary_source) -> tuple:
        if sort is JobSort.SALARY_DESC:
            return (
                case((JobORM.salary_max_k.is_(None), 1), else_=0).asc(),
                JobORM.salary_max_k.desc(),
                JobORM.salary_min_k.desc(),
                JobORM.id.asc(),
            )
        if sort is JobSort.SALARY_ASC:
            return (
                case((JobORM.salary_min_k.is_(None), 1), else_=0).asc(),
                JobORM.salary_min_k.asc(),
                JobORM.salary_max_k.asc(),
                JobORM.id.asc(),
            )
        return (
            primary_source.last_seen_at.desc(),
            JobORM.id.asc(),
        )

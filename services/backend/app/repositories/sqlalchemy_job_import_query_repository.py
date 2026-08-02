"""SQLAlchemy implementation of the Job Import audit query port."""
from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.job_import_queries.models import (
    JobImportDetail,
    JobImportErrorDetail,
    JobImportItemDetail,
)
from app.application.ports.job_import_query_repository import (
    AbstractJobImportQueryRepository,
)
from app.db.models import JobImportItemORM, JobImportORM

SessionFactory = Callable[[], Session]


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _require_utc(value: datetime) -> datetime:
    normalized = _as_utc(value)
    assert normalized is not None
    return normalized


def _public_errors(errors: list[dict[str, Any]]) -> tuple[JobImportErrorDetail, ...]:
    """Project only public error fields; deliberately discard raw input data."""

    result: list[JobImportErrorDetail] = []
    for error in errors:
        result.append(
            JobImportErrorDetail(
                index=int(error["index"]),
                stage=str(error["stage"]),
                code=str(error["code"]),
                message=str(error["message"]),
            )
        )
    return tuple(result)


class SqlAlchemyJobImportQueryRepository(AbstractJobImportQueryRepository):
    """Read one completed import audit using a short-lived Session."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def get_import(self, import_id: str) -> JobImportDetail | None:
        with self._session_factory() as session:
            batch = session.execute(
                select(
                    JobImportORM.id,
                    JobImportORM.source_version,
                    JobImportORM.collector_version,
                    JobImportORM.received,
                    JobImportORM.created,
                    JobImportORM.updated,
                    JobImportORM.skipped,
                    JobImportORM.errors,
                    JobImportORM.search_intent_snapshot,
                    JobImportORM.source_snapshot,
                    JobImportORM.collected_at,
                    JobImportORM.created_at,
                ).where(JobImportORM.id == import_id)
            ).one_or_none()
            if batch is None:
                return None

            item_rows = session.execute(
                select(
                    JobImportItemORM.input_index,
                    JobImportItemORM.outcome,
                    JobImportItemORM.job_id,
                    JobImportItemORM.job_source_id,
                    JobImportItemORM.error_code,
                    JobImportItemORM.error_message,
                )
                .where(JobImportItemORM.import_id == import_id)
                .order_by(JobImportItemORM.input_index.asc())
            ).all()

        return JobImportDetail(
            import_id=batch.id,
            source_version=batch.source_version,
            collector_version=batch.collector_version,
            received=batch.received,
            created=batch.created,
            updated=batch.updated,
            skipped=batch.skipped,
            errors=_public_errors(batch.errors),
            search_intent_snapshot=deepcopy(batch.search_intent_snapshot),
            source_snapshot=deepcopy(batch.source_snapshot),
            collected_at=_as_utc(batch.collected_at),
            created_at=_require_utc(batch.created_at),
            items=tuple(
                JobImportItemDetail(
                    input_index=row.input_index,
                    outcome=row.outcome,
                    job_id=row.job_id,
                    job_source_id=row.job_source_id,
                    error_code=row.error_code,
                    error_message=row.error_message,
                )
                for row in item_rows
            ),
        )

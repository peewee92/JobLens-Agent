"""SQLAlchemy persistence for Application Workspaces."""
from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.application_workspace.models import (
    ApplicationWorkspace,
    ApplicationWorkspaceSourceSnapshot,
    ApplicationWorkspaceStatus,
)
from app.db.models import ApplicationWorkspaceORM

SessionFactory = Callable[[], Session]


class SqlAlchemyApplicationWorkspaceRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def get(self, workspace_id: str) -> ApplicationWorkspace | None:
        with self._session_factory() as session:
            record = session.get(ApplicationWorkspaceORM, workspace_id)
            return _restore(record) if record is not None else None

    def get_by_actor_and_idempotency_key(
        self, actor_id: str, idempotency_key: str
    ) -> ApplicationWorkspace | None:
        with self._session_factory() as session:
            record = session.scalar(
                select(ApplicationWorkspaceORM).where(
                    ApplicationWorkspaceORM.actor_id == actor_id,
                    ApplicationWorkspaceORM.idempotency_key == idempotency_key,
                )
            )
            return _restore(record) if record is not None else None

    def add(self, workspace: ApplicationWorkspace) -> ApplicationWorkspace:
        with self._session_factory() as session, session.begin():
            record = ApplicationWorkspaceORM(
                id=workspace.workspace_id,
                job_id=workspace.job_id,
                actor_id=workspace.actor_id,
                idempotency_key=workspace.idempotency_key,
                status=workspace.status.value,
                profile_id=workspace.source_snapshot.profile_id,
                profile_version=workspace.source_snapshot.profile_version,
                search_intent_id=workspace.source_snapshot.search_intent_id,
                search_intent_version=workspace.source_snapshot.search_intent_version,
                requirement_extraction_id=workspace.source_snapshot.requirement_extraction_id,
                match_report_id=workspace.source_snapshot.match_report_id,
                current_fact_fingerprint=workspace.current_fact_fingerprint,
                created_at=workspace.created_at,
                updated_at=workspace.updated_at,
            )
            session.add(record)
            session.flush()
            return _restore(record)


def _restore(record: ApplicationWorkspaceORM) -> ApplicationWorkspace:
    return ApplicationWorkspace(
        workspace_id=record.id,
        job_id=record.job_id,
        actor_id=record.actor_id,
        idempotency_key=record.idempotency_key,
        status=ApplicationWorkspaceStatus(record.status),
        source_snapshot=ApplicationWorkspaceSourceSnapshot(
            profile_id=record.profile_id,
            profile_version=record.profile_version,
            search_intent_id=record.search_intent_id,
            search_intent_version=record.search_intent_version,
            requirement_extraction_id=record.requirement_extraction_id,
            match_report_id=record.match_report_id,
        ),
        current_fact_fingerprint=record.current_fact_fingerprint,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )

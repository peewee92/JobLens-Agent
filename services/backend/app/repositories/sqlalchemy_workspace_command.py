"""Short local write transaction; no models or external calls inside."""
from contextlib import contextmanager
from sqlalchemy.exc import SQLAlchemyError
from app.application.application_workspace.transaction import WorkspacePersistenceError
from app.repositories.sqlalchemy_application_workspace_repository import (
    SqlAlchemyApplicationWorkspaceRepository, SqlAlchemyApplicationTimelineRepository,
    SqlAlchemyExecutionActionRepository, SqlAlchemyEvidenceProposalRepository)
from app.repositories.sqlalchemy_career_context_repository import (
    SqlAlchemyCareerContextRepository, SqlAlchemyCareerContextQueryRepository)


class SqlAlchemyWorkspaceCommandUnitOfWork:
    def __init__(self, factory):
        self._factory = factory

    def __enter__(self):
        self._session = self._factory()
        try:
            if self._session.get_bind().dialect.name == 'sqlite':
                self._session.connection().exec_driver_sql('BEGIN IMMEDIATE')
            else:
                self._session.begin()
            self.workspaces = SqlAlchemyApplicationWorkspaceRepository(session=self._session)
            self.timeline = SqlAlchemyApplicationTimelineRepository(session=self._session)
            self.actions = SqlAlchemyExecutionActionRepository(session=self._session)
            self.proposals = SqlAlchemyEvidenceProposalRepository(session=self._session)
            self.profile_writer = SqlAlchemyCareerContextRepository(self._session)
            @contextmanager
            def borrowed():
                yield self._session
            self.profiles = SqlAlchemyCareerContextQueryRepository(borrowed)
            from app.repositories.sqlalchemy_evidence_sources import SqlAlchemyEvidenceActionSources
            self.evidence_sources = SqlAlchemyEvidenceActionSources(self._session)
            return self
        except SQLAlchemyError as exc:
            self._session.close()
            raise WorkspacePersistenceError('workspace_transaction_unavailable') from exc

    def commit(self):
        self._session.commit()

    def __exit__(self, exc_type, exc, tb):
        try:
            self._session.rollback()
        finally:
            self._session.close()
        if exc_type and issubclass(exc_type, SQLAlchemyError):
            raise WorkspacePersistenceError('workspace_transaction_save_failed') from exc

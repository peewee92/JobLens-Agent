"""Resolve origins inside the command's caller-owned read/write snapshot."""
from contextlib import contextmanager
from app.application.application_workspace.evidence_context import EvidenceActionSource, EvidenceContext
from app.application.application_workspace.evidence_proposal import EvidenceProposalBlockedError
from app.application.saved_career_analysis import SavedCareerAnalysis
from app.application.application_workspace.start_analysis_execution import analysis_source_snapshot
from app.repositories.sqlalchemy_job_requirement_repository import SqlAlchemyJobRequirementQueryRepository
from app.repositories.sqlalchemy_application_workspace_repository import SqlAlchemyApplicationWorkspaceRepository, SqlAlchemyExecutionActionRepository
from app.repositories.sqlalchemy_career_context_repository import SqlAlchemyCareerContextQueryRepository
from app.db.models import CareerAgentRunORM
from app.domain.job_requirements import RequirementType


class SqlAlchemyEvidenceActionSources:
    def __init__(self, session):
        self._session = session

    def resolve(self, action, workspace):
        snapshot = workspace.source_snapshot
        thread, result_id = action.source_analysis_thread_id, action.source_analysis_result_id
        if bool(thread) != bool(result_id):
            raise EvidenceProposalBlockedError('evidence_proposal_action_source_invalid')
        if thread:
            row = self._session.get(CareerAgentRunORM, thread)
            try:
                result = SavedCareerAnalysis.from_payload(row.analysis_result) if row and row.analysis_result else None
            except (ValueError, TypeError, KeyError) as exc:
                raise EvidenceProposalBlockedError('evidence_proposal_action_source_invalid') from exc
            if result is None or result.result_id != result_id or workspace.job_id not in result.inputs.selected_job_ids:
                raise EvidenceProposalBlockedError('evidence_proposal_action_source_invalid')
            binding = next((b for b in result.bindings if b.job_id == workspace.job_id), None)
            if binding is None:
                raise EvidenceProposalBlockedError('evidence_proposal_action_source_invalid')
            snapshot = analysis_source_snapshot(result, binding)
        @contextmanager
        def borrowed():
            yield self._session
        extraction = SqlAlchemyJobRequirementQueryRepository(borrowed).get_extraction(
            job_id=workspace.job_id, extraction_id=snapshot.requirement_extraction_id)
        if extraction is None or not set(action.source_requirement_ids) <= {r.id for r in extraction.requirements}:
            raise EvidenceProposalBlockedError('evidence_proposal_action_source_invalid')
        options = tuple((r.id, r.normalized_capability.strip()) for r in extraction.requirements
            if r.id in action.source_requirement_ids and r.type is RequirementType.SKILL and r.normalized_capability and r.normalized_capability.strip())
        return EvidenceActionSource(action.action_id, snapshot.profile_id, snapshot.profile_version,
            snapshot.requirement_extraction_id, thread, result_id, options)


class SqlAlchemyEvidenceContextQuery:
    def __init__(self, factory):
        self._factory = factory

    def read(self, workspace_id):
        with self._factory() as session:
            if session.get_bind().dialect.name == 'sqlite':
                session.connection().exec_driver_sql('BEGIN')
            workspace = SqlAlchemyApplicationWorkspaceRepository(session=session).get(workspace_id)
            if workspace is None:
                raise EvidenceProposalBlockedError('application_workspace_not_found')
            @contextmanager
            def borrowed():
                yield session
            current = SqlAlchemyCareerContextQueryRepository(borrowed).get_current_profile()
            resolver = SqlAlchemyEvidenceActionSources(session)
            sources, blocked = [], []
            for action in SqlAlchemyExecutionActionRepository(session=session).list_for_workspace(workspace_id):
                if action.status.value != 'done':
                    continue
                try:
                    source = resolver.resolve(action, workspace)
                    if source.options:
                        sources.append(source)
                    else:
                        blocked.append(action.action_id)
                except EvidenceProposalBlockedError:
                    blocked.append(action.action_id)
            return EvidenceContext(current.id if current else None, current.version if current else None,
                tuple(sources), tuple(blocked))

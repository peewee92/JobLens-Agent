"""One local read snapshot for the original run scope and current versioned facts."""
from contextlib import contextmanager
from app.application.analysis_update import AnalysisUpdatePlanError, UpdateFacts, UpdateJobFacts
from app.application.saved_career_analysis import SavedCareerAnalysis
from app.agent.graph.state import CareerAgentState
from app.db.models import CareerAgentRunORM, ApplicationWorkspaceORM
from app.repositories.sqlalchemy_career_context_repository import SqlAlchemyCareerContextQueryRepository
from app.repositories.sqlalchemy_job_query_repository import SqlAlchemyJobQueryRepository
from app.repositories.sqlalchemy_job_requirement_repository import SqlAlchemyJobRequirementQueryRepository
from app.repositories.sqlalchemy_match_report_repository import SqlAlchemyMatchReportQueryRepository


class SqlAlchemyAnalysisUpdateReader:
    def __init__(self, factory):
        self._factory = factory

    def read_initial_scope(self, job_ids, *, session=None):
        ids = tuple(dict.fromkeys(job_ids))
        if not 1 <= len(ids) <= 50:
            raise AnalysisUpdatePlanError('analysis_update_scope_invalid')
        if session is None:
            with self._factory() as owned:
                if owned.get_bind().dialect.name == 'sqlite':
                    owned.connection().exec_driver_sql('BEGIN')
                return self.read_initial_scope(ids, session=owned)
        @contextmanager
        def borrowed():
            yield session
        context = SqlAlchemyCareerContextQueryRepository(borrowed).get_current_context()
        jobs = SqlAlchemyJobQueryRepository(borrowed)
        requirements = SqlAlchemyJobRequirementQueryRepository(borrowed)
        reports = {r.report.job_id: r for r in SqlAlchemyMatchReportQueryRepository(borrowed).list_latest_for_jobs(ids)}
        return UpdateFacts('', '', 'batch', 0, context, tuple(
            UpdateJobFacts(job_id, jobs.get_job(job_id), requirements.get_latest(job_id), reports.get(job_id))
            for job_id in ids))

    def read(self, thread_id, scope, *, session=None):
        if session is None:
            with self._factory() as owned:
                if owned.get_bind().dialect.name == 'sqlite':
                    owned.connection().exec_driver_sql('BEGIN')
                return self.read(thread_id, scope, session=owned)
        return self._read(thread_id, scope, session)


    def read_legacy_workspace(self, workspace_id, *, session=None):
        if session is None:
            with self._factory() as owned:
                if owned.get_bind().dialect.name == 'sqlite':
                    owned.connection().exec_driver_sql('BEGIN')
                return self.read_legacy_workspace(workspace_id, session=owned)
        workspace = session.get(ApplicationWorkspaceORM, workspace_id)
        if workspace is None:
            raise AnalysisUpdatePlanError('application_workspace_not_found')
        if workspace.current_analysis_thread_id is not None or workspace.current_analysis_result_id is not None:
            raise AnalysisUpdatePlanError('application_workspace_has_saved_analysis')
        @contextmanager
        def borrowed():
            yield session
        context = SqlAlchemyCareerContextQueryRepository(borrowed).get_current_context()
        jobs = SqlAlchemyJobQueryRepository(borrowed)
        requirements = SqlAlchemyJobRequirementQueryRepository(borrowed)
        reports = SqlAlchemyMatchReportQueryRepository(borrowed).list_latest_for_jobs((workspace.job_id,))
        report = next(iter(reports), None)
        return UpdateFacts(workspace_id, '', 'targets', 0, context,
            (UpdateJobFacts(workspace.job_id, jobs.get_job(workspace.job_id),
                            requirements.get_latest(workspace.job_id), report),))

    def _read(self, thread_id, scope, session):
        row = session.get(CareerAgentRunORM, thread_id)
        if row is None or row.analysis_result is None:
            raise AnalysisUpdatePlanError('analysis_update_result_missing')
        result = SavedCareerAnalysis.from_payload(row.analysis_result)
        state = CareerAgentState.from_payload(row.payload)
        ids = result.inputs.selected_job_ids if scope == 'targets' else state.requested_job_ids
        ids = tuple(dict.fromkeys(ids))
        @contextmanager
        def borrowed():
            yield session
        context = SqlAlchemyCareerContextQueryRepository(borrowed).get_current_context()
        jobs = SqlAlchemyJobQueryRepository(borrowed)
        requirements = SqlAlchemyJobRequirementQueryRepository(borrowed)
        reports = {r.report.job_id: r for r in SqlAlchemyMatchReportQueryRepository(borrowed).list_latest_for_jobs(ids)}
        return UpdateFacts(thread_id, result.result_id, scope, result.inputs.profile_version, context,
            tuple(UpdateJobFacts(job_id, jobs.get_job(job_id), requirements.get_latest(job_id), reports.get(job_id)) for job_id in ids))

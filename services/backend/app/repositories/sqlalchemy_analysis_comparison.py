"""One read snapshot of two saved results and their explicit immutable report IDs."""
from contextlib import contextmanager
from pydantic import ValidationError
from app.application.analysis_comparison import AnalysisComparisonError, SavedComparisonSide
from app.application.saved_career_analysis import SavedCareerAnalysis
from app.agent.graph.state import CareerAgentState, CareerAgentStatus
from app.db.models import CareerAgentRunORM
from app.repositories.sqlalchemy_match_report_repository import SqlAlchemyMatchReportQueryRepository


class SqlAlchemyAnalysisComparisonReader:
    def __init__(self, factory):
        self.factory = factory

    def read(self, thread_id):
        with self.factory() as session:
            if session.get_bind().dialect.name == 'sqlite':
                session.connection().exec_driver_sql('BEGIN')
            row = session.get(CareerAgentRunORM, thread_id)
            if row is None:
                raise AnalysisComparisonError('analysis_comparison_run_missing')
            try:
                state = CareerAgentState.from_payload(row.payload)
                if not state.update_source_thread_id or not state.update_source_result_id:
                    raise AnalysisComparisonError('analysis_comparison_not_update')
                source = session.get(CareerAgentRunORM, state.update_source_thread_id)
                if source is None or source.analysis_result is None:
                    raise AnalysisComparisonError('analysis_comparison_source_missing')
                if row.analysis_result is None:
                    raise AnalysisComparisonError('analysis_comparison_result_missing')
                old_state = CareerAgentState.from_payload(source.payload)
                old_result = SavedCareerAnalysis.from_payload(source.analysis_result)
                result = SavedCareerAnalysis.from_payload(row.analysis_result)
            except (ValidationError, KeyError, TypeError, ValueError) as exc:
                if isinstance(exc, AnalysisComparisonError):
                    raise
                raise AnalysisComparisonError('analysis_comparison_binding_invalid') from exc
            if state.status is not CareerAgentStatus.COMPLETED or old_state.status is not CareerAgentStatus.COMPLETED:
                raise AnalysisComparisonError('analysis_comparison_result_missing')
            @contextmanager
            def borrowed():
                yield session
            repo = SqlAlchemyMatchReportQueryRepository(borrowed)
            cache = {}
            for binding in (*old_result.bindings, *result.bindings):
                if binding.match_report_id not in cache:
                    try:
                        report = repo.get(binding.match_report_id)
                    except (ValidationError, KeyError, TypeError, ValueError) as exc:
                        raise AnalysisComparisonError('analysis_comparison_binding_invalid') from exc
                    cache[binding.match_report_id] = report
            reports = {key: value for key, value in cache.items() if value is not None}
            return (SavedComparisonSide(old_state, old_result, reports), SavedComparisonSide(state, result, reports))

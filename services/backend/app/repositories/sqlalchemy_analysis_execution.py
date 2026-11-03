"""A short caller-owned transaction for starting preparation; no external work."""
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from app.agent.graph.checkpoint_port import CheckpointPersistenceError
from app.application.saved_career_analysis import SavedCareerAnalysis
from app.application.application_workspace.start_analysis_execution import AnalysisExecutionResult, LOCAL_ACTOR_ID
from app.db.models import CareerAgentRunORM, AnalysisExecutionReceiptORM
from app.repositories.sqlalchemy_application_workspace_repository import (
    SqlAlchemyApplicationWorkspaceRepository, SqlAlchemyApplicationTimelineRepository,
    SqlAlchemyResumeVariantRepository, SqlAlchemyExecutionActionRepository,
)


class SqlAlchemyAnalysisExecutionUnitOfWork:
    def __init__(self, factory, *, facts):
        self._factory, self._facts = factory, facts

    def __enter__(self):
        self._session = self._factory()
        try:
            if self._session.get_bind().dialect.name == "sqlite":
                self._session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            else:
                self._session.begin()
            self.workspaces = SqlAlchemyApplicationWorkspaceRepository(session=self._session)
            self.timeline = SqlAlchemyApplicationTimelineRepository(session=self._session)
            self.variants = SqlAlchemyResumeVariantRepository(session=self._session)
            self.actions = SqlAlchemyExecutionActionRepository(session=self._session)
            return self
        except Exception:
            self._session.close()
            raise

    def __exit__(self, exc_type, exc, tb):
        try:
            self._session.rollback()
        finally:
            self._session.close()
        if exc_type and issubclass(exc_type, SQLAlchemyError):
            raise CheckpointPersistenceError("开始执行保存失败，事务已回滚；请查看工作区后使用原请求重试") from exc

    def commit(self):
        self._session.commit()

    def find_receipt(self, actor_id, command_id):
        return self._session.scalar(select(AnalysisExecutionReceiptORM).where(
            AnalysisExecutionReceiptORM.actor_id == actor_id, AnalysisExecutionReceiptORM.command_id == command_id))

    def load_analysis(self, thread_id):
        record = self._session.get(CareerAgentRunORM, thread_id)
        return (SavedCareerAnalysis.from_payload(record.analysis_result), record.status) if record and record.analysis_result else (None, None)

    def stale_reasons(self, inputs):
        return self._facts.stale_reasons(inputs, session=self._session)

    def save_receipt(self, *, actor_id, command, response):
        self._session.add(AnalysisExecutionReceiptORM(actor_id=actor_id, command_id=command.command_id,
            thread_id=command.thread_id, command_digest=command.digest(), response=response.to_payload()))
        self._session.flush()


class SqlAlchemyAnalysisExecutionQuery:
    def __init__(self, factory):
        self._factory = factory

    def for_thread(self, thread_id):
        with self._factory() as session:
            receipts = session.scalars(select(AnalysisExecutionReceiptORM).where(
                AnalysisExecutionReceiptORM.thread_id == thread_id,
                AnalysisExecutionReceiptORM.actor_id == LOCAL_ACTOR_ID
            ).order_by(AnalysisExecutionReceiptORM.id.desc())).all()
            if not receipts:
                return None
            latest = AnalysisExecutionResult.from_payload(receipts[0].response)
            by_job = {}
            for receipt in receipts:
                result = AnalysisExecutionResult.from_payload(receipt.response)
                if result.result_id != latest.result_id:
                    continue
                for item in result.items:
                    by_job.setdefault(item.job_id, item)
            record = session.get(CareerAgentRunORM, thread_id)
            analysis = SavedCareerAnalysis.from_payload(record.analysis_result) if record and record.analysis_result else None
            order = analysis.inputs.selected_job_ids if analysis and analysis.result_id == latest.result_id else tuple(by_job)
            return AnalysisExecutionResult(latest.thread_id, latest.result_id, latest.command_id,
                tuple(by_job[key] for key in order if key in by_job))



class SqlAlchemyWorkspacePreparationReader:
    def __init__(self, factory, *, facts):
        self._factory, self._facts = factory, facts

    def read(self, workspace):
        from app.application.application_workspace.saved_preparation import SavedWorkspacePreparation
        from app.application.application_workspace.start_analysis_execution import analysis_source_snapshot
        with self._factory() as session:
            record = session.get(CareerAgentRunORM, workspace.current_analysis_thread_id)
            if record is None or not record.analysis_result:
                raise LookupError("application_workspace_saved_materials_missing")
            result = SavedCareerAnalysis.from_payload(record.analysis_result)
            if result.result_id != workspace.current_analysis_result_id or workspace.job_id not in result.inputs.selected_job_ids:
                raise LookupError("application_workspace_saved_materials_mismatch")
            bundle = next((item for item in result.preparations if item.job_id == workspace.job_id), None)
            binding = next((item for item in result.bindings if item.job_id == workspace.job_id), None)
            if bundle is None or binding is None or not bundle.facts_usable:
                raise LookupError("application_workspace_saved_materials_missing")
        return SavedWorkspacePreparation(result.thread_id, result.result_id, analysis_source_snapshot(result, binding),
            bundle, self._facts.stale_reasons(result.inputs))

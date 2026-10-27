"""Bounded read-only projection over existing career and runtime facts."""
from contextlib import contextmanager
from sqlalchemy import select, func
from app.agent.graph.state import CareerAgentState
from app.application.workbench import WorkbenchSnapshot, WorkbenchRun, WorkbenchWorkspace, WorkbenchChange
from app.application.saved_career_analysis import SavedCareerAnalysis
from app.application.career_context.release import GetCareerContextReleaseReadinessUseCase
from app.application.application_workspace.start_analysis_execution import LOCAL_ACTOR_ID
from app.db.models import (CareerAgentRunORM, ApplicationWorkspaceORM, ApplicationTimelineEventORM,
    ExecutionActionItemORM, JobORM)
from app.repositories.sqlalchemy_career_context_repository import SqlAlchemyCareerContextQueryRepository


class SqlAlchemyWorkbenchQuery:
    def __init__(self, factory, *, facts):
        self._factory, self._facts = factory, facts

    def read(self):
        with self._factory() as session:
            if session.get_bind().dialect.name == "sqlite":
                session.connection().exec_driver_sql("BEGIN")
            @contextmanager
            def borrowed():
                yield session
            context_query = SqlAlchemyCareerContextQueryRepository(borrowed)
            context = context_query.get_current_context()
            readiness = GetCareerContextReleaseReadinessUseCase(context_query).execute()
            profile, intent = context.profile, context.search_intent
            job_count = session.scalar(select(func.count()).select_from(JobORM))
            record = session.scalar(select(CareerAgentRunORM).order_by(
                CareerAgentRunORM.updated_at.desc(), CareerAgentRunORM.thread_id).limit(1))
            current = None
            if record:
                state = CareerAgentState.from_payload(record.payload)
                analysis = SavedCareerAnalysis.from_payload(record.analysis_result) if record.analysis_result else None
                execution_count = session.scalar(select(func.count(func.distinct(ApplicationWorkspaceORM.job_id))).where(
                    ApplicationWorkspaceORM.actor_id == LOCAL_ACTOR_ID,
                    ApplicationWorkspaceORM.current_analysis_thread_id == record.thread_id,
                    ApplicationWorkspaceORM.current_analysis_result_id == analysis.result_id)) if analysis else 0
                current = WorkbenchRun(record.thread_id, record.status, record.current_step,
                    len(state.requested_job_ids), len(state.confirmed_target_job_ids), execution_count,
                    analysis.result_id if analysis else None,
                    not bool(self._facts.stale_reasons(analysis.inputs, session=session)) if analysis else None, record.updated_at,
                    state.update_partial, sum(s.status in {"completed", "reused"} for s in state.update_steps) if state.update_steps else len(state.ranked_job_ids))
            workspaces = []
            rows = session.scalars(select(ApplicationWorkspaceORM).where(ApplicationWorkspaceORM.actor_id == LOCAL_ACTOR_ID)
                .order_by(ApplicationWorkspaceORM.updated_at.desc(), ApplicationWorkspaceORM.id).limit(5)).all()
            for row in rows:
                job = session.get(JobORM, row.job_id)
                count = session.scalar(select(func.count()).select_from(ExecutionActionItemORM).where(
                    ExecutionActionItemORM.workspace_id == row.id, ExecutionActionItemORM.status.in_(("todo", "in_progress"))))
                workspaces.append(WorkbenchWorkspace(row.id, row.job_id, job.title if job else "原岗位记录已不可用",
                    row.status, count, row.current_analysis_thread_id))
            changes = [WorkbenchChange(event.event_type, event.created_at, f"/applications/{event.workspace_id}")
                for event in session.scalars(select(ApplicationTimelineEventORM).join(ApplicationWorkspaceORM,
                    ApplicationWorkspaceORM.id == ApplicationTimelineEventORM.workspace_id)
                    .where(ApplicationWorkspaceORM.actor_id == LOCAL_ACTOR_ID).order_by(
                        ApplicationTimelineEventORM.created_at.desc(), ApplicationTimelineEventORM.id.desc()).limit(10))]
            if profile:
                changes.append(WorkbenchChange("profile_confirmed", profile.created_at, "/profile"))
            if intent:
                changes.append(WorkbenchChange("search_intent_confirmed", intent.created_at, "/profile"))
            if record:
                changes.append(WorkbenchChange("analysis_partial" if state.update_partial and state.result_id else f"analysis_{record.status}", record.updated_at,
                    f"/agent?threadId={record.thread_id}"))
            # SQLite restores some timestamps without timezone, normalize only for ordering.
            from datetime import UTC
            changes.sort(key=lambda e: e.occurred_at.replace(tzinfo=UTC).timestamp(), reverse=True)
            return WorkbenchSnapshot(profile.version if profile else None, intent.version if intent else None,
                len(profile.evidence) if profile else 0, tuple(item.code.value for item in readiness.blockers),
                job_count, current, tuple(workspaces), tuple(changes[:10]))

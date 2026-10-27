"""Atomic runtime transactions using the application's primary Session factory."""
from dataclasses import replace
from collections.abc import Callable
from contextlib import contextmanager
import time
from uuid import uuid4
from pathlib import Path

from sqlalchemy import inspect, select, update, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.agent.graph.checkpoint_port import CheckpointConflictError, CheckpointNotReadyError, CheckpointPersistenceError, next_revision
from app.agent.graph.legacy_checkpoint import load_legacy_checkpoint
from app.agent.graph.state import CareerAgentState, CareerAgentStatus
from app.application.saved_career_analysis import SavedCareerAnalysis
from app.db.models import CareerAgentRunORM, CareerAgentRunEventORM
from app.db.models.common import utc_now


class SqlAlchemyCareerAgentCheckpointStore:
    def __init__(self, session_factory: Callable[[], Session], *, legacy_path: str | Path | None = None, clock: Callable[[], float] = time.time):
        self._factory = session_factory
        self._now = clock
        self._legacy_path = Path(legacy_path) if legacy_path is not None else None
        with self._factory() as session:
            bind = session.get_bind()
            if bind.url.get_backend_name() == "sqlite" and bind.url.database not in (None, "", ":memory:"):
                if not Path(bind.url.database).is_file():
                    raise CheckpointNotReadyError("主数据库不存在，请先配置并迁移数据库；读取运行不会创建空数据库")
            inspector = inspect(bind)
            if not all(inspector.has_table(name) for name in ("career_agent_runs", "career_agent_run_events")):
                raise CheckpointNotReadyError("运行存储尚未迁移，请先在数据库副本验证并升级到最新版本")
            columns = {item["name"] for item in inspector.get_columns("career_agent_runs")}
            if not {"lease_token", "lease_expires_at", "analysis_result"} <= columns:
                raise CheckpointNotReadyError("运行恢复与分析结果存储尚未迁移，请先在数据库副本验证并升级到最新版本")

    def transition(self, previous: CareerAgentState | None, candidate: CareerAgentState) -> CareerAgentState:
        return self._transition(previous, candidate, lease_token=None)

    def _transition(self, previous: CareerAgentState | None, candidate: CareerAgentState, *, lease_token: str | None, analysis: SavedCareerAnalysis | None = None, validate=None, match_write=None, validate_match=None) -> CareerAgentState:
        state = next_revision(previous, candidate)
        if previous is not None and match_write is None and any(
            old.status != "completed" and new.status == "completed"
            for old, new in zip(previous.update_steps, candidate.update_steps, strict=True)
        ):
            raise CheckpointConflictError("步骤完成必须与匹配报告在同一事务提交")
        if previous is None and load_legacy_checkpoint(self._legacy_path, state.thread_id) is not None:
            raise CheckpointConflictError("旧运行标识仅供历史查看，请使用新的运行标识重新分析")
        analysis_payload = analysis.to_payload() if analysis is not None else None
        if analysis is not None:
            if previous is None or (analysis.thread_id, analysis.run_id, analysis.result_id) != (
                state.thread_id, state.run_id, state.result_id
            ) or state.status is not CareerAgentStatus.COMPLETED or validate is None:
                raise CheckpointConflictError("分析结果与运行身份不一致")
            expected = (previous.profile_id, previous.profile_version, previous.search_intent_id,
                previous.search_intent_version, previous.current_match_report_ids, previous.confirmed_target_job_ids)
            inputs = analysis.inputs
            if (inputs.profile_id, inputs.profile_version, inputs.search_intent_id,
                inputs.search_intent_version, inputs.match_report_ids, inputs.selected_job_ids) != expected:
                raise CheckpointConflictError("分析结果不能替换本次已绑定的事实或目标")
        elif state.result_id is not None and (previous is None or state.result_id != previous.result_id):
            raise CheckpointConflictError("结果引用只能与完整结果一起保存")
        try:
            with self._factory() as session, session.begin():
                if match_write is not None:
                    if previous is None or lease_token is None or validate_match is None:
                        raise CheckpointConflictError("匹配提交必须由有效运行领取")
                    if session.get_bind().dialect.name == "sqlite":
                        session.connection().exec_driver_sql("BEGIN IMMEDIATE")
                    if validate_match(previous, session=session):
                        state = next_revision(previous, replace(previous, status=CareerAgentStatus.STALE,
                            current_step="update_inputs_changed", pending_approval=False))
                    else:
                        from app.repositories.sqlalchemy_match_report_repository import SqlAlchemyMatchReportRepository
                        report_id, report = match_write
                        completed = [step for old, step in zip(previous.update_steps, state.update_steps, strict=True)
                                     if step != old and step.status == "completed" and step.report_id == report_id]
                        if len(completed) != 1:
                            raise CheckpointConflictError("匹配提交缺少唯一完成步骤")
                        step = completed[0]
                        if (report.job_id, report.profile_id, report.profile_version, report.search_intent_id,
                            report.search_intent_version, report.extraction_id, report.policy_version, report.provider_calls) != (
                            step.job_id, state.profile_id, state.profile_version, state.search_intent_id,
                            state.search_intent_version, step.extraction_id, state.update_policy_version, 0):
                            raise CheckpointConflictError("匹配结果不能替换固定事实或使用模型")
                        SqlAlchemyMatchReportRepository(session).add(report, report_id=report_id)
                if analysis is not None:
                    if session.get_bind().dialect.name == "sqlite":
                        session.connection().exec_driver_sql("BEGIN IMMEDIATE")
                    if validate(analysis.inputs, session=session):
                        state = next_revision(previous, replace(candidate, status=CareerAgentStatus.STALE,
                            current_step="analysis_facts_changed", pending_approval=False))
                payload = state.to_payload()
                if previous is None:
                    session.add(CareerAgentRunORM(thread_id=state.thread_id, run_id=state.run_id,
                        request_id=state.request_id, revision=state.revision, status=state.status.value,
                        current_step=state.current_step, payload=payload))
                    session.flush()
                else:
                    changed = session.execute(update(CareerAgentRunORM).where(
                        CareerAgentRunORM.thread_id == previous.thread_id,
                        CareerAgentRunORM.run_id == previous.run_id,
                        CareerAgentRunORM.request_id == previous.request_id,
                        CareerAgentRunORM.revision == previous.revision,
                        CareerAgentRunORM.status == previous.status.value,
                        CareerAgentRunORM.current_step == previous.current_step,
                        *([CareerAgentRunORM.analysis_result.is_(None)] if analysis is not None else []),
                        (
                            (CareerAgentRunORM.lease_token == lease_token) &
                            (CareerAgentRunORM.lease_expires_at > self._now())
                            if lease_token is not None else
                            or_(CareerAgentRunORM.lease_token.is_(None), CareerAgentRunORM.lease_expires_at <= self._now())
                        ),
                    ).values(revision=state.revision, status=state.status.value,
                             current_step=state.current_step, payload=payload, updated_at=utc_now(),
                             **({"analysis_result": analysis_payload} if analysis is not None else {})))
                    if changed.rowcount != 1:
                        raise CheckpointConflictError("运行已被其他请求推进，请读取最新状态")
                session.add(CareerAgentRunEventORM(thread_id=state.thread_id, revision=state.revision, payload=payload))
                session.flush()
        except IntegrityError as exc:
            # Constraint failures are not all competing writes (e.g. a trigger
            # can abort an event insert). Do not tell users another writer won.
            if getattr(exc.orig, "sqlite_errorcode", None) in {1555, 2067}:
                raise CheckpointConflictError("运行或修订已存在，请读取最新状态") from exc
            raise CheckpointPersistenceError("运行保存失败，本次事务已回滚；请读取状态后显式继续") from exc
        return state

    def load(self, *, thread_id: str) -> CareerAgentState | None:
        with self._factory() as session:
            record = session.get(CareerAgentRunORM, thread_id)
            if record is not None:
                return CareerAgentState.from_payload(record.payload)
        return load_legacy_checkpoint(self._legacy_path, thread_id)

    def load_analysis(self, *, thread_id: str) -> SavedCareerAnalysis | None:
        with self._factory() as session:
            record = session.get(CareerAgentRunORM, thread_id)
            return SavedCareerAnalysis.from_payload(record.analysis_result) if record is not None and record.analysis_result else None

    def recent_runs(self, *, limit: int = 10) -> tuple[CareerAgentState, ...]:
        if not 1 <= limit <= 20:
            raise ValueError("recent run limit must be 1..20")
        with self._factory() as session:
            rows = session.scalars(select(CareerAgentRunORM).order_by(
                CareerAgentRunORM.updated_at.desc(), CareerAgentRunORM.thread_id.desc()).limit(limit)).all()
            return tuple(CareerAgentState.from_payload(row.payload) for row in rows)

    def load_payload(self, *, thread_id: str) -> dict | None:
        state = self.load(thread_id=thread_id)
        return state.to_payload() if state else None

    def load_history(self, *, thread_id: str) -> tuple[CareerAgentState, ...]:
        with self._factory() as session:
            events = session.scalars(select(CareerAgentRunEventORM).where(
                CareerAgentRunEventORM.thread_id == thread_id).order_by(CareerAgentRunEventORM.id)).all()
            return tuple(CareerAgentState.from_payload(event.payload) for event in events)


    @contextmanager
    def execution(self, *, thread_id: str, lease_seconds: float = 120):
        """Claim with a short transaction; never keep a DB transaction around work."""
        if lease_seconds <= 0:
            raise ValueError("lease duration must be positive")
        token = uuid4().hex
        now = self._now()
        with self._factory() as session, session.begin():
            acquired = session.execute(update(CareerAgentRunORM).where(
                CareerAgentRunORM.thread_id == thread_id,
                or_(CareerAgentRunORM.lease_token.is_(None), CareerAgentRunORM.lease_expires_at <= now),
            ).values(lease_token=token, lease_expires_at=now + lease_seconds))
            if acquired.rowcount != 1:
                raise CheckpointConflictError("运行正在执行或不存在，请读取状态后再继续")
        try:
            yield _LeasedCheckpointStore(self, token)
        finally:
            with self._factory() as session, session.begin():
                session.execute(update(CareerAgentRunORM).where(
                    CareerAgentRunORM.thread_id == thread_id,
                    CareerAgentRunORM.lease_token == token,
                ).values(lease_token=None, lease_expires_at=None))


class _LeasedCheckpointStore:
    """Only this claimed writer may commit until expiry; no token in public state."""
    def __init__(self, store, token):
        self._store, self._token = store, token

    def transition(self, previous, candidate):
        if previous is None:
            raise CheckpointConflictError("执行前必须先保存运行记录")
        return self._store._transition(previous, candidate, lease_token=self._token)

    def complete_analysis(self, previous, candidate, analysis, *, validate):
        return self._store._transition(previous, candidate, lease_token=self._token,
            analysis=analysis, validate=validate)

    def complete_update_match(self, previous, candidate, report_id, report, *, validate):
        return self._store._transition(previous, candidate, lease_token=self._token,
            match_write=(report_id, report), validate_match=validate)

    def assert_execution(self):
        with self._store._factory() as session:
            active = session.scalar(select(CareerAgentRunORM.thread_id).where(
                CareerAgentRunORM.lease_token == self._token,
                CareerAgentRunORM.lease_expires_at > self._store._now()))
        if active is None:
            raise CheckpointConflictError("执行租约已失效，请读取状态后显式继续")

    def load(self, *, thread_id):
        return self._store.load(thread_id=thread_id)

    def load_payload(self, *, thread_id):
        return self._store.load_payload(thread_id=thread_id)

    def load_history(self, *, thread_id):
        return self._store.load_history(thread_id=thread_id)

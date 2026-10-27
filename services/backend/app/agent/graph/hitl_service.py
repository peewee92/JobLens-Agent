"""Application-facing seam for the first durable Career Agent HITL flow."""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal
from contextlib import nullcontext

from app.application.saved_career_analysis import BuildSavedCareerAnalysisUseCase
from app.agent.context import CareerAgentContextBuilder
from app.agent.graph.checkpoint_port import CareerAgentCheckpointStore, CheckpointConflictError
from app.agent.graph.command_digest import start_command_digest, update_command_digest
from app.agent.graph.hitl_decision import HumanDecisionRequest, TargetCohortDecisionHandler
from app.agent.graph.langgraph_rank_interrupt import LangGraphRankToTargetCohortInterrupt
from app.agent.graph.resume_stale_guard import ResumeStaleGuard
from app.agent.graph.skill_gap_resume import SkillGapResumeExecutor
from app.agent.graph.state import CareerAgentState, CareerAgentStatus, UpdateMatchStep
from app.agent.graph.update_matching import UpdateBatchRequest, batch_replayed
from app.application.match_policy_version import CURRENT_MATCH_POLICY_VERSION
from app.agent.tool_registry import CareerAgentToolRegistry


@dataclass(frozen=True, slots=True)
class StartCareerAgentRunRequest:
    thread_id: str
    run_id: str
    request_id: str
    job_ids: tuple[str, ...]
    top_n: int = 3


@dataclass(frozen=True, slots=True)
class UpdateCareerAgentRunRequest:
    thread_id: str
    run_id: str
    request_id: str
    source_thread_id: str
    source_result_id: str
    scope: Literal["targets", "batch"]
    input_digest: str
    top_n: int = 3


@dataclass(frozen=True, slots=True)
class ResumeCareerAgentRunRequest:
    thread_id: str
    interrupt_id: str
    action_id: str
    decision: Literal["approve", "edit", "reject"]
    selected_job_ids: tuple[str, ...] = ()


class CareerAgentHitlService:
    """Expose Run/Get/Resume without leaking LangGraph types into the API layer."""

    def __init__(
        self,
        *,
        checkpoints: CareerAgentCheckpointStore,
        context_builder: CareerAgentContextBuilder,
        tool_registry: CareerAgentToolRegistry,
        analysis: BuildSavedCareerAnalysisUseCase | None = None,
        update_planner=None,
        update_executor=None,
    ) -> None:
        self._update_executor = update_executor
        self._update_planner = update_planner
        self._analysis = analysis
        self._checkpoints = checkpoints
        self._context_builder = context_builder
        self._tool_registry = tool_registry
        self._rank_interrupt = LangGraphRankToTargetCohortInterrupt(
            tool_registry=tool_registry,
            checkpoints=checkpoints,
        )
        self._decisions = TargetCohortDecisionHandler(checkpoints=checkpoints)
        self._stale_guard = ResumeStaleGuard(
            checkpoints=checkpoints,
            context_builder=context_builder,
            tool_registry=tool_registry,
        )
        self._gap_resume = SkillGapResumeExecutor(
            checkpoints=checkpoints,
            context_builder=context_builder,
            tool_registry=tool_registry,
            analysis=analysis,
        )

    def start(self, request: StartCareerAgentRunRequest) -> CareerAgentState:
        existing = self._checkpoints.load(thread_id=request.thread_id)
        if existing is not None:
            if existing.run_id == request.run_id and existing.request_id == request.request_id:
                digest = start_command_digest(
                    thread_id=request.thread_id, run_id=request.run_id, request_id=request.request_id,
                    job_ids=request.job_ids, top_n=request.top_n,
                )
                if existing.legacy_read_only or existing.start_command_digest is None:
                    raise CheckpointConflictError("旧运行没有可验证的命令内容，请新建分析；原状态仍可查看")
                if existing.start_command_digest != digest:
                    raise CheckpointConflictError("请求标识已用于不同分析内容，请读取原运行或使用新标识")
                return existing
            raise ValueError("career agent thread already exists")
        context = self._context_builder.build()
        if hasattr(self._checkpoints, "execution"):
            # Persist the accepted request before attempting any workflow.
            if not 1 <= request.top_n <= 5 or not 1 <= len(set(request.job_ids)) <= 50:
                raise ValueError("analysis requires 1..50 jobs and top_n 1..5")
            initial = CareerAgentState(
                thread_id=request.thread_id, run_id=request.run_id, request_id=request.request_id,
                status=CareerAgentStatus.CREATED, current_step="analysis_created",
                goal="analyze_target_cohort_gaps", requested_job_ids=tuple(dict.fromkeys(request.job_ids)),
                requested_top_n=request.top_n,
                start_command_digest=start_command_digest(thread_id=request.thread_id,
                    run_id=request.run_id, request_id=request.request_id,
                    job_ids=request.job_ids, top_n=request.top_n),
                profile_id=context.profile.id if context.profile else None,
                profile_version=context.profile.version if context.profile else None,
                search_intent_id=context.search_intent.id if context.search_intent else None,
                search_intent_version=context.search_intent.version if context.search_intent else None,
            )
            self._checkpoints.transition(None, initial)
            return self.continue_run(thread_id=request.thread_id)
        # Frozen standalone adapter compatibility, not the production dependency.
        return self._rank_interrupt.run(
            context=context,
            thread_id=request.thread_id,
            run_id=request.run_id,
            request_id=request.request_id,
            job_ids=request.job_ids,
            top_n=request.top_n,
        )

    def start_update(self, request: UpdateCareerAgentRunRequest) -> CareerAgentState:
        """Accept only already-compatible reports; never start Match or a provider here."""
        from dataclasses import asdict
        digest = update_command_digest(**asdict(request))
        existing = self.get_state(thread_id=request.thread_id)
        if existing is not None:
            if (existing.run_id, existing.request_id, existing.start_command_digest) != (
                request.run_id, request.request_id, digest):
                raise CheckpointConflictError("更新请求标识已用于不同内容，请查看原运行")
            return existing  # Receipt replay is not an implicit Continue.
        if self._update_planner is None or not 1 <= request.top_n <= 5:
            raise CheckpointConflictError("当前服务不支持此更新，请重新预检")
        plan = self._update_planner.execute(thread_id=request.source_thread_id, scope=request.scope)
        if (plan.source_result_id, plan.input_digest) != (request.source_result_id, request.input_digest):
            raise CheckpointConflictError("预检后的事实已变化，请重新预检；没有启动更新")
        if not plan.items or plan.profile_id is None or plan.search_intent_id is None or self._update_executor is None:
            raise CheckpointConflictError("请先确认职业资料与意向，再重新预检")
        statuses = {"reuse": "reused", "ready": "pending", "deferred": "pending",
                    "requires_model": "requires_model", "input_blocked": "input_blocked"}
        steps = tuple(UpdateMatchStep(i.job_id, i.extraction_id, i.input_fingerprint, i.base_report_id,
            statuses[i.status], report_id=i.reusable_report_id,
            error_code=i.blocker_codes[0] if i.blocker_codes else None) for i in plan.items)
        initial = CareerAgentState(thread_id=request.thread_id, run_id=request.run_id,
            request_id=request.request_id, status=CareerAgentStatus.CREATED, current_step="analysis_created",
            goal="analyze_target_cohort_gaps", requested_job_ids=tuple(i.job_id for i in plan.items),
            requested_top_n=request.top_n, start_command_digest=digest,
            profile_id=plan.profile_id, profile_version=plan.profile_version,
            search_intent_id=plan.search_intent_id, search_intent_version=plan.search_intent_version,
            update_source_thread_id=plan.source_thread_id, update_source_result_id=plan.source_result_id,
            update_scope=plan.scope, update_input_digest=plan.input_digest,
            update_report_ids=tuple(i.reusable_report_id for i in plan.items if i.reusable_report_id),
            update_steps=steps, update_policy_version=CURRENT_MATCH_POLICY_VERSION)
        try:
            self._checkpoints.transition(None, initial)
        except CheckpointConflictError:
            # Concurrent identical acceptance returns the same durable receipt.
            existing = self.get_state(thread_id=request.thread_id)
            if existing is not None and existing.start_command_digest == digest:
                return existing
            raise
        return self.continue_run(thread_id=request.thread_id, update_command=UpdateBatchRequest(
            action_id=f"initial:{request.request_id}", expected_revision=0))

    def get_state(self, *, thread_id: str) -> CareerAgentState | None:
        return self._checkpoints.load(thread_id=thread_id)

    def get_result(self, *, thread_id: str):
        query = getattr(self._checkpoints, "load_analysis", None)
        return query(thread_id=thread_id) if query else None

    def result_stale_reasons(self, result):
        return self._analysis.facts.stale_reasons(result.inputs) if self._analysis else ("currentness_unavailable",)

    def recent_runs(self, *, limit: int = 10) -> tuple[CareerAgentState, ...]:
        if not 1 <= limit <= 20:
            raise ValueError("recent run limit must be 1..20")
        query = getattr(self._checkpoints, "recent_runs", None)
        return query(limit=limit) if query else ()

    def _scope(self, thread_id: str):
        execution = getattr(self._checkpoints, "execution", None)
        return execution(thread_id=thread_id) if execution else nullcontext(self._checkpoints)

    def _scoped(self, checkpoints):
        return CareerAgentHitlService(checkpoints=checkpoints,
            context_builder=self._context_builder, tool_registry=self._tool_registry, analysis=self._analysis, update_planner=self._update_planner, update_executor=self._update_executor)

    def resume(self, request: ResumeCareerAgentRunRequest) -> CareerAgentState:
        with self._scope(request.thread_id) as scoped:
            service = self._scoped(scoped)
            decided = service._decisions.submit(HumanDecisionRequest(
                thread_id=request.thread_id, interrupt_id=request.interrupt_id,
                action_id=request.action_id, decision=request.decision,
                selected_job_ids=request.selected_job_ids,
            ))
            if decided.status is not CareerAgentStatus.RESUMING:
                return decided
            return service._continue_resuming(request.thread_id)

    def _continue_resuming(self, thread_id: str) -> CareerAgentState:
        validated = self._stale_guard.validate(thread_id=thread_id)
        if validated.status is not CareerAgentStatus.RESUMING:
            return validated
        return self._gap_resume.execute(thread_id=thread_id)

    def continue_run(self, *, thread_id: str, update_command: UpdateBatchRequest | None = None) -> CareerAgentState:
        state = self.get_state(thread_id=thread_id)
        if state is None:
            raise ValueError("career agent thread does not exist")
        if state.legacy_read_only:
            raise CheckpointConflictError("旧运行仅供查看，请新建分析")
        if state.update_steps and batch_replayed(state, update_command):
            return state
        if state.status not in {CareerAgentStatus.CREATED, CareerAgentStatus.RUNNING, CareerAgentStatus.RESUMING}:
            return state
        with self._scope(thread_id) as scoped:
            service = self._scoped(scoped)
            state = scoped.load(thread_id=thread_id)
            if state.status is CareerAgentStatus.RESUMING:
                return service._continue_resuming(thread_id)
            if state.status not in {CareerAgentStatus.CREATED, CareerAgentStatus.RUNNING}:
                return state
            context = self._context_builder.build()
            profile, intent = context.profile, context.search_intent
            current_versions = (profile.id if profile else None, profile.version if profile else None,
                                intent.id if intent else None, intent.version if intent else None)
            expected = (state.profile_id, state.profile_version, state.search_intent_id, state.search_intent_version)
            if current_versions != expected:
                return scoped.transition(state, replace(state, status=CareerAgentStatus.STALE,
                    current_step="continue_stale_career_context", pending_approval=False))
            if state.update_steps and state.current_step in {"analysis_created", "update_matching"}:
                if self._update_executor is None:
                    raise CheckpointConflictError("缺少更新执行服务，请检查配置")
                state = self._update_executor.execute(state, scoped, update_command)
                if state.status is CareerAgentStatus.STALE:
                    return state
                if not state.update_partial and any(step.status not in {"completed", "reused"} for step in state.update_steps):
                    return state
                return service._rank_interrupt.run(context=context, thread_id=state.thread_id,
                    run_id=state.run_id, request_id=state.request_id, job_ids=state.requested_job_ids,
                    top_n=state.requested_top_n, initial_state=state)
            if state.status is CareerAgentStatus.CREATED and state.update_source_thread_id:
                plan = self._update_planner.execute(thread_id=state.update_source_thread_id, scope=state.update_scope)
                if plan.input_digest != state.update_input_digest:
                    return scoped.transition(state, replace(state, status=CareerAgentStatus.STALE,
                        current_step="update_inputs_changed", pending_approval=False))
            if state.status is CareerAgentStatus.RUNNING:
                if state.current_step != "rank_jobs" or not state.current_match_report_ids or not state.proposed_target_job_ids:
                    raise CheckpointConflictError("没有可继续的已保存排序，请新建分析")
                # Ranking was saved before the crash; do not run it again.
                return service._rank_interrupt.continue_saved_ranking(state)
            return service._rank_interrupt.run(context=context, thread_id=state.thread_id,
                run_id=state.run_id, request_id=state.request_id, job_ids=state.requested_job_ids,
                top_n=state.requested_top_n, initial_state=state)


__all__ = [
    "CareerAgentHitlService",
    "ResumeCareerAgentRunRequest",
    "StartCareerAgentRunRequest",
]

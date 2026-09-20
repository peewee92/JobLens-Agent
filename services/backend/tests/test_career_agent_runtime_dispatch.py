"""Runtime dispatch tests for Career Agent vNext 1.1."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from app.agent.context import CareerAgentContext, CareerAgentProfileContext
from app.agent.governed_loop_runtime import (
    CareerAgentGovernedLoopResult,
    CareerAgentGovernedLoopStatus,
)
from app.agent.graph.checkpoint import SQLiteCareerAgentCheckpointStore
from app.agent.graph.hitl_service import (
    CareerAgentHitlService,
    ResumeCareerAgentRunRequest,
)
from app.agent.graph.state import CareerAgentState, CareerAgentStatus
from app.agent.intent import (
    CareerIntent,
    CareerIntentGoal,
    CareerIntentResolutionContext,
    CareerIntentValidationError,
)
from app.agent.tool_registry import CareerAgentToolRegistry
from app.agent.runtime_dispatch import (
    CareerAgentDurableRunIdentity,
    CareerAgentRuntimeDispatchError,
    CareerAgentRuntimeDispatchKind,
    CareerAgentRuntimeDispatchRequest,
    CareerAgentRuntimeDispatcher,
)
from app.application.match_report.models import (
    MatchRecommendation,
    MatchReport,
    StoredMatchReport,
)


class _GovernedRuntime:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def run(self, **kwargs: object) -> CareerAgentGovernedLoopResult:
        self.calls.append(kwargs)
        return CareerAgentGovernedLoopResult(
            status=CareerAgentGovernedLoopStatus.COMPLETED,
            tool_results=(),
            trace=(),
        )


class _HitlService:
    def __init__(self) -> None:
        self.calls: list[object] = []

    def start(self, request: object) -> CareerAgentState:
        self.calls.append(request)
        return CareerAgentState(
            thread_id=getattr(request, "thread_id"),
            run_id=getattr(request, "run_id"),
            request_id=getattr(request, "request_id"),
            status=CareerAgentStatus.INTERRUPTED,
            current_step="target_cohort_confirmation",
            goal="analyze_batch_and_gaps",
            requested_job_ids=tuple(getattr(request, "job_ids")),
            proposed_target_job_ids=tuple(getattr(request, "job_ids"))[:2],
            pending_approval=True,
            interrupt_id="interrupt-1",
        )


@dataclass
class _RealContextBuilder:
    profile_version: int = 3

    def build(self) -> CareerAgentContext:
        return CareerAgentContext(
            usable=True,
            confirmation_boundary="confirmed",
            profile=CareerAgentProfileContext(
                id="profile_1",
                version=self.profile_version,
                headline="AI engineer",
                years_of_experience=8,
                skills=(),
            ),
            search_intent=None,
            current_job=None,
            relevant_evidence=(),
            blockers=(),
            blocker_messages=(),
        )


@dataclass
class _RealRankingWorkflow:
    reports: tuple[StoredMatchReport, ...]
    calls: int = 0

    def execute(self, job_ids, *, include_blocked=False, top_n=None):
        self.calls += 1
        reports = tuple(item for item in self.reports if item.report.job_id in job_ids)
        return reports if top_n is None else reports[:top_n]


@dataclass(frozen=True)
class _RealGapResult:
    cohort_id: str
    job_ids: tuple[str, ...]
    facts_usable: bool = True
    blockers: tuple[str, ...] = ()
    provider_calls: int = 0
    db_writes: int = 0


@dataclass
class _RealGapWorkflow:
    calls: int = 0

    def execute(self, command):
        self.calls += 1
        return _RealGapResult(
            cohort_id=command.cohort_id,
            job_ids=command.selected_job_ids,
        )


class _UnusedWorkflow:
    def execute(self, *args, **kwargs):  # pragma: no cover
        raise AssertionError("unrelated workflow must not run")


def _stored(report_id: str, job_id: str) -> StoredMatchReport:
    return StoredMatchReport(
        id=report_id,
        report=MatchReport(
            job_id=job_id,
            profile_id="profile_1",
            profile_version=3,
            extraction_id=f"ext_{job_id}",
            eligibility=None,  # type: ignore[arg-type]
            recommendation=MatchRecommendation.STRONG,
            summary="grounded",
            strengths=(),
            risks=(),
            requirement_results=(),
            matched_requirement_ids=(),
            partial_requirement_ids=(),
            missing_requirement_ids=(),
            evidence_links=(),
            matcher_version="fixture",
            prompt_version="fixture",
            model=None,
            trace_run_id=None,
        ),
        created_at=datetime.now(UTC),
    )


def _context() -> CareerAgentContext:
    return CareerAgentContext(
        usable=True,
        confirmation_boundary="confirmed_profile_and_search_intent",
        profile=None,
        search_intent=None,
        current_job=None,
        relevant_evidence=(),
        blockers=(),
        blocker_messages=(),
    )


def test_dispatches_rank_then_gaps_to_existing_durable_hitl_runtime() -> None:
    governed = _GovernedRuntime()
    hitl = _HitlService()
    dispatcher = CareerAgentRuntimeDispatcher(
        governed_runtime=governed,
        hitl_service=hitl,
    )

    result = dispatcher.run(
        CareerAgentRuntimeDispatchRequest(
            user_message="先选最值得投的岗位，再分析共同差距",
            intent=CareerIntent(
                goals=(CareerIntentGoal.RANK_JOBS, CareerIntentGoal.REVIEW_GAPS),
                reasoning_summary="先排序，再确认目标岗位并分析差距。",
            ),
            context=_context(),
            resolution_context=CareerIntentResolutionContext(
                run_job_ids=("job-1", "job-2", "job-3")
            ),
            durable_run=CareerAgentDurableRunIdentity(
                thread_id="thread-1",
                run_id="run-1",
                request_id="request-1",
                top_n=2,
            ),
        )
    )

    assert result.kind is CareerAgentRuntimeDispatchKind.DURABLE_HITL
    assert result.durable_state is not None
    assert result.durable_state.status is CareerAgentStatus.INTERRUPTED
    assert result.loop_result is None
    assert governed.calls == []
    assert len(hitl.calls) == 1
    start = hitl.calls[0]
    assert getattr(start, "job_ids") == ("job-1", "job-2", "job-3")
    assert getattr(start, "top_n") == 2


def test_dispatches_simple_goal_to_governed_loop_with_already_resolved_intent() -> None:
    governed = _GovernedRuntime()
    hitl = _HitlService()
    dispatcher = CareerAgentRuntimeDispatcher(
        governed_runtime=governed,
        hitl_service=hitl,
    )

    result = dispatcher.run(
        CareerAgentRuntimeDispatchRequest(
            user_message="这批岗位排个序",
            intent=CareerIntent(
                goals=(CareerIntentGoal.RANK_JOBS,),
                reasoning_summary="只排序。",
            ),
            context=_context(),
            resolution_context=CareerIntentResolutionContext(run_job_ids=("job-1",)),
        )
    )

    assert result.kind is CareerAgentRuntimeDispatchKind.GOVERNED_LOOP
    assert result.loop_result is not None
    assert result.durable_state is None
    assert len(governed.calls) == 1
    call = governed.calls[0]
    assert call["resolved_intent"].goals == (CareerIntentGoal.RANK_JOBS,)
    assert hitl.calls == []


def test_durable_hitl_dispatch_uses_explicit_grounded_job_subset() -> None:
    governed = _GovernedRuntime()
    hitl = _HitlService()
    dispatcher = CareerAgentRuntimeDispatcher(
        governed_runtime=governed,
        hitl_service=hitl,
    )

    dispatcher.run(
        CareerAgentRuntimeDispatchRequest(
            user_message="只分析 job-2 和 job-3，然后看差距",
            intent=CareerIntent(
                goals=(CareerIntentGoal.RANK_JOBS, CareerIntentGoal.REVIEW_GAPS),
                referenced_job_ids=("job-2", "job-3"),
            ),
            context=_context(),
            resolution_context=CareerIntentResolutionContext(
                run_job_ids=("job-1", "job-2", "job-3")
            ),
            durable_run=CareerAgentDurableRunIdentity(
                thread_id="thread-subset",
                run_id="run-subset",
                request_id="request-subset",
            ),
        )
    )

    assert len(hitl.calls) == 1
    assert getattr(hitl.calls[0], "job_ids") == ("job-2", "job-3")
    assert governed.calls == []


def test_durable_hitl_dispatch_rejects_job_outside_governed_scope() -> None:
    governed = _GovernedRuntime()
    hitl = _HitlService()
    dispatcher = CareerAgentRuntimeDispatcher(
        governed_runtime=governed,
        hitl_service=hitl,
    )

    try:
        dispatcher.run(
            CareerAgentRuntimeDispatchRequest(
                user_message="分析 job-2",
                intent=CareerIntent(
                    goals=(CareerIntentGoal.RANK_JOBS, CareerIntentGoal.REVIEW_GAPS),
                    referenced_job_ids=("job-2",),
                ),
                context=_context(),
                resolution_context=CareerIntentResolutionContext(run_job_ids=("job-1",)),
                durable_run=CareerAgentDurableRunIdentity(
                    thread_id="thread-outside",
                    run_id="run-outside",
                    request_id="request-outside",
                ),
            )
        )
    except CareerIntentValidationError as exc:
        assert "outside the governed run scope" in str(exc)
    else:  # pragma: no cover - regression guard
        raise AssertionError("runtime dispatch must reject out-of-scope jobs")

    assert hitl.calls == []
    assert governed.calls == []


def test_dispatcher_composes_real_durable_rank_interrupt_and_gap_resume(tmp_path) -> None:
    context_builder = _RealContextBuilder()
    ranking = _RealRankingWorkflow(
        reports=(
            _stored("mr_1", "job-1"),
            _stored("mr_2", "job-2"),
        )
    )
    gaps = _RealGapWorkflow()
    registry = CareerAgentToolRegistry(
        ranking=ranking,
        target_cohort_gaps=gaps,  # type: ignore[arg-type]
        job_preparation=_UnusedWorkflow(),
    )
    hitl = CareerAgentHitlService(
        checkpoints=SQLiteCareerAgentCheckpointStore(tmp_path / "dispatch.sqlite3"),
        context_builder=context_builder,  # type: ignore[arg-type]
        tool_registry=registry,
    )
    governed = _GovernedRuntime()
    dispatcher = CareerAgentRuntimeDispatcher(
        governed_runtime=governed,
        hitl_service=hitl,
    )

    dispatched = dispatcher.run(
        CareerAgentRuntimeDispatchRequest(
            user_message="先选最值得投的，再确认后分析差距",
            intent=CareerIntent(
                goals=(CareerIntentGoal.RANK_JOBS, CareerIntentGoal.REVIEW_GAPS),
            ),
            context=context_builder.build(),
            resolution_context=CareerIntentResolutionContext(
                run_job_ids=("job-1", "job-2")
            ),
            durable_run=CareerAgentDurableRunIdentity(
                thread_id="thread-real-dispatch",
                run_id="run-real-dispatch",
                request_id="request-real-dispatch",
                top_n=1,
            ),
        )
    )

    assert dispatched.kind is CareerAgentRuntimeDispatchKind.DURABLE_HITL
    assert dispatched.durable_state is not None
    assert dispatched.durable_state.status is CareerAgentStatus.INTERRUPTED
    assert dispatched.durable_state.pending_approval is True
    assert dispatched.durable_state.interrupt_id is not None
    assert ranking.calls == 1
    assert gaps.calls == 0
    assert governed.calls == []

    completed = hitl.resume(
        ResumeCareerAgentRunRequest(
            thread_id="thread-real-dispatch",
            interrupt_id=dispatched.durable_state.interrupt_id,
            action_id="approve-real-dispatch",
            decision="approve",
        )
    )

    assert completed.status is CareerAgentStatus.COMPLETED
    assert completed.current_step == "skill_gap_completed"
    assert completed.confirmed_target_job_ids == ("job-1",)
    assert ranking.calls == 2  # initial ranking + stale validation readback
    assert gaps.calls == 1
    assert completed.provider_call_count == 0


def test_durable_hitl_dispatch_requires_explicit_run_identity_before_execution() -> None:
    governed = _GovernedRuntime()
    hitl = _HitlService()
    dispatcher = CareerAgentRuntimeDispatcher(
        governed_runtime=governed,
        hitl_service=hitl,
    )

    try:
        dispatcher.run(
            CareerAgentRuntimeDispatchRequest(
                user_message="排序后看差距",
                intent=CareerIntent(
                    goals=(CareerIntentGoal.RANK_JOBS, CareerIntentGoal.REVIEW_GAPS),
                ),
                context=_context(),
                resolution_context=CareerIntentResolutionContext(run_job_ids=("job-1",)),
            )
        )
    except CareerAgentRuntimeDispatchError as exc:
        assert "durable run identity" in str(exc)
    else:  # pragma: no cover - regression guard
        raise AssertionError("durable dispatch must require explicit run identity")

    assert governed.calls == []
    assert hitl.calls == []

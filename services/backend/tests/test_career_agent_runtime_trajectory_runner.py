from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from app.agent.context import CareerAgentContext, CareerAgentProfileContext
from app.agent.graph.checkpoint import SQLiteCareerAgentCheckpointStore
from app.agent.graph.hitl_decision import HumanDecisionRequest, TargetCohortDecisionHandler
from app.agent.graph.langgraph_rank_interrupt import LangGraphRankToTargetCohortInterrupt
from app.agent.graph.resume_stale_guard import ResumeStaleGuard
from app.agent.graph.skill_gap_resume import SkillGapResumeExecutor
from app.agent.graph.state import CareerAgentStatus
from app.agent.tool_registry import CareerAgentToolRegistry
from app.application.match_report.models import MatchRecommendation, MatchReport, StoredMatchReport
from app.evals.career_agent_runtime_runner import (
    CareerAgentRuntimeTrajectoryRequest,
    CareerAgentRuntimeTrajectoryRunner,
)


@dataclass
class _ContextBuilder:
    context: CareerAgentContext

    def build(self) -> CareerAgentContext:
        return self.context


@dataclass
class _RankingWorkflow:
    reports: tuple[StoredMatchReport, ...]

    def execute(self, job_ids, *, include_blocked=False, top_n=None):
        reports = tuple(item for item in self.reports if item.report.job_id in job_ids)
        return reports if top_n is None else reports[:top_n]


@dataclass(frozen=True)
class _GapResult:
    cohort_id: str
    job_ids: tuple[str, ...]
    facts_usable: bool = True
    blockers: tuple[str, ...] = ()
    provider_calls: int = 0
    db_writes: int = 0


@dataclass
class _GapWorkflow:
    calls: int = 0

    def execute(self, command):
        self.calls += 1
        return _GapResult(cohort_id=command.cohort_id, job_ids=command.selected_job_ids)


class _UnusedWorkflow:
    def execute(self, *args, **kwargs):  # pragma: no cover
        raise AssertionError("unrelated workflow must not run")


def _context(*, profile_version: int = 3) -> CareerAgentContext:
    return CareerAgentContext(
        usable=True,
        confirmation_boundary="confirmed",
        profile=CareerAgentProfileContext(
            id="profile_1",
            version=profile_version,
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


def _runner(tmp_path, *, reports, context_builder, gaps):
    store = SQLiteCareerAgentCheckpointStore(tmp_path / "runner.sqlite3")
    registry = CareerAgentToolRegistry(
        ranking=_RankingWorkflow(reports=reports),
        target_cohort_gaps=gaps,  # type: ignore[arg-type]
        job_preparation=_UnusedWorkflow(),
    )
    return CareerAgentRuntimeTrajectoryRunner(
        checkpoints=store,
        rank_interrupt=LangGraphRankToTargetCohortInterrupt(
            checkpoints=store,
            tool_registry=registry,
        ),
        decisions=TargetCohortDecisionHandler(checkpoints=store),
        stale_guard=ResumeStaleGuard(
            checkpoints=store,
            context_builder=context_builder,
            tool_registry=registry,
        ),
        gap_resume=SkillGapResumeExecutor(
            checkpoints=store,
            context_builder=context_builder,
            tool_registry=registry,
        ),
    )


def test_runner_drives_real_approve_handlers_and_duplicate_resume(tmp_path) -> None:
    context = _context()
    gaps = _GapWorkflow()
    runner = _runner(
        tmp_path,
        reports=(_stored("mr_1", "job_1"), _stored("mr_2", "job_2")),
        context_builder=_ContextBuilder(context),
        gaps=gaps,
    )
    interrupt_id = "interrupt_" + __import__("hashlib").sha256(
        b"thread_approve:run_approve:target_cohort_confirmation"
    ).hexdigest()[:24]

    case = runner.run(
        CareerAgentRuntimeTrajectoryRequest(
            case_id="real_approve",
            context=context,
            thread_id="thread_approve",
            run_id="run_approve",
            request_id="request_approve",
            job_ids=("job_1", "job_2"),
            top_n=2,
            decision=HumanDecisionRequest(
                thread_id="thread_approve",
                interrupt_id=interrupt_id,
                action_id="action_approve",
                decision="approve",
            ),
            replay_resume=True,
            expected_status=CareerAgentStatus.COMPLETED,
            expected_nodes=(
                "rank_jobs",
                "target_cohort_confirmation",
                "target_cohort_resume",
                "skill_gap_ready",
                "skill_gap_completed",
            ),
        )
    )

    assert case.snapshot.state.status is CareerAgentStatus.COMPLETED
    assert case.snapshot.visited_nodes == case.expected_nodes
    assert case.snapshot.state.provider_call_count == 0
    assert case.snapshot.business_state_writes == 0
    assert gaps.calls == 1


def test_runner_drives_real_reject_and_missing_match_paths(tmp_path) -> None:
    context = _context()
    gaps = _GapWorkflow()
    runner = _runner(
        tmp_path,
        reports=(_stored("mr_1", "job_1"),),
        context_builder=_ContextBuilder(context),
        gaps=gaps,
    )
    interrupt_id = "interrupt_" + __import__("hashlib").sha256(
        b"thread_reject:run_reject:target_cohort_confirmation"
    ).hexdigest()[:24]

    rejected = runner.run(
        CareerAgentRuntimeTrajectoryRequest(
            case_id="real_reject",
            context=context,
            thread_id="thread_reject",
            run_id="run_reject",
            request_id="request_reject",
            job_ids=("job_1",),
            decision=HumanDecisionRequest(
                thread_id="thread_reject",
                interrupt_id=interrupt_id,
                action_id="action_reject",
                decision="reject",
            ),
            expected_status=CareerAgentStatus.CANCELLED,
            expected_nodes=("rank_jobs", "target_cohort_confirmation", "target_cohort_rejected"),
        )
    )
    assert rejected.snapshot.visited_nodes == rejected.expected_nodes
    assert gaps.calls == 0

    missing = runner.run(
        CareerAgentRuntimeTrajectoryRequest(
            case_id="real_missing_match",
            context=context,
            thread_id="thread_missing",
            run_id="run_missing",
            request_id="request_missing",
            job_ids=("job_missing",),
            expected_status=CareerAgentStatus.BLOCKED,
            expected_nodes=("match_not_ready",),
        )
    )
    assert missing.snapshot.state.status is CareerAgentStatus.BLOCKED
    assert missing.snapshot.visited_nodes == ("match_not_ready",)
    assert gaps.calls == 0


def test_runner_records_real_stale_profile_without_gap(tmp_path) -> None:
    initial_context = _context(profile_version=3)
    context_builder = _ContextBuilder(_context(profile_version=4))
    gaps = _GapWorkflow()
    runner = _runner(
        tmp_path,
        reports=(_stored("mr_1", "job_1"),),
        context_builder=context_builder,
        gaps=gaps,
    )
    interrupt_id = "interrupt_" + __import__("hashlib").sha256(
        b"thread_stale:run_stale:target_cohort_confirmation"
    ).hexdigest()[:24]

    case = runner.run(
        CareerAgentRuntimeTrajectoryRequest(
            case_id="real_stale_profile",
            context=initial_context,
            thread_id="thread_stale",
            run_id="run_stale",
            request_id="request_stale",
            job_ids=("job_1",),
            decision=HumanDecisionRequest(
                thread_id="thread_stale",
                interrupt_id=interrupt_id,
                action_id="action_stale",
                decision="approve",
            ),
            expected_status=CareerAgentStatus.STALE,
            expected_nodes=(
                "rank_jobs",
                "target_cohort_confirmation",
                "target_cohort_resume",
                "resume_stale_profile",
            ),
        )
    )

    assert case.snapshot.state.status is CareerAgentStatus.STALE
    assert case.snapshot.visited_nodes == case.expected_nodes
    assert gaps.calls == 0

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
from app.agent.tool_registry import CareerAgentToolName, CareerAgentToolRegistry
from app.application.match_report.models import MatchRecommendation, MatchReport, StoredMatchReport


@dataclass
class _ContextBuilder:
    calls: int = 0

    def build(self) -> CareerAgentContext:
        self.calls += 1
        return CareerAgentContext(
            usable=True,
            confirmation_boundary="confirmed",
            profile=CareerAgentProfileContext(
                id="profile_1",
                version=3,
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
class _RankingWorkflow:
    reports: tuple[StoredMatchReport, ...]
    calls: int = 0

    def execute(self, job_ids, *, include_blocked=False, top_n=None):
        self.calls += 1
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
    def execute(self, *args, **kwargs):  # pragma: no cover - must stay unreachable
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


def _registry(ranking: _RankingWorkflow, gaps: _GapWorkflow) -> CareerAgentToolRegistry:
    return CareerAgentToolRegistry(
        ranking=ranking,
        target_cohort_gaps=gaps,  # type: ignore[arg-type]
        job_preparation=_UnusedWorkflow(),
    )


def test_durable_hitl_survives_store_recreation_and_duplicate_resume(tmp_path) -> None:
    database_path = tmp_path / "agent.sqlite3"
    reports = (_stored("mr_1", "job_1"), _stored("mr_2", "job_2"), _stored("mr_3", "job_3"))
    ranking = _RankingWorkflow(reports=reports)
    gaps = _GapWorkflow()
    context_builder = _ContextBuilder()
    registry = _registry(ranking, gaps)

    interrupted = LangGraphRankToTargetCohortInterrupt(
        checkpoints=SQLiteCareerAgentCheckpointStore(database_path),
        tool_registry=registry,
    ).run(
        context=context_builder.build(),
        thread_id="thread_restart",
        run_id="run_restart",
        request_id="request_restart",
        job_ids=("job_1", "job_2", "job_3"),
        top_n=2,
    )
    assert interrupted.status is CareerAgentStatus.INTERRUPTED
    assert interrupted.interrupt_id

    decided = TargetCohortDecisionHandler(
        checkpoints=SQLiteCareerAgentCheckpointStore(database_path)
    ).submit(
        HumanDecisionRequest(
            thread_id="thread_restart",
            interrupt_id=interrupted.interrupt_id,
            action_id="action_restart",
            decision="edit",
            selected_job_ids=("job_3", "job_1"),
        )
    )
    assert decided.status is CareerAgentStatus.RESUMING

    validated = ResumeStaleGuard(
        checkpoints=SQLiteCareerAgentCheckpointStore(database_path),
        context_builder=context_builder,
        tool_registry=registry,
    ).validate(thread_id="thread_restart")
    assert validated.current_step == "skill_gap_ready"

    first = SkillGapResumeExecutor(
        checkpoints=SQLiteCareerAgentCheckpointStore(database_path),
        context_builder=context_builder,
        tool_registry=registry,
    ).execute(thread_id="thread_restart")
    assert first.status is CareerAgentStatus.COMPLETED
    assert first.confirmed_target_job_ids == ("job_3", "job_1")
    assert first.provider_call_count == 0
    assert gaps.calls == 1

    replay = SkillGapResumeExecutor(
        checkpoints=SQLiteCareerAgentCheckpointStore(database_path),
        context_builder=context_builder,
        tool_registry=registry,
    ).execute(thread_id="thread_restart")
    assert replay == first
    assert gaps.calls == 1

    restored = SQLiteCareerAgentCheckpointStore(database_path).load(thread_id="thread_restart")
    assert restored == first
    assert restored is not None
    assert restored.current_step == "skill_gap_completed"
    assert ranking.calls == 2

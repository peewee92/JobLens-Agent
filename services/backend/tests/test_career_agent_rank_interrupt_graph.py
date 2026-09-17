from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from app.agent.context import CareerAgentContext, CareerAgentProfileContext
from app.agent.graph.checkpoint import SQLiteCareerAgentCheckpointStore
from app.agent.graph.langgraph_rank_interrupt import LangGraphRankToTargetCohortInterrupt
from app.agent.graph.rank_interrupt import RankToTargetCohortInterrupt
from app.agent.graph.state import CareerAgentStatus
from app.agent.tool_registry import CareerAgentToolRegistry
from app.application.match_report.models import MatchRecommendation, MatchReport, StoredMatchReport


@dataclass
class _RankingWorkflow:
    reports: tuple[StoredMatchReport, ...]
    calls: list[tuple[tuple[str, ...], bool, int | None]]

    def execute(self, job_ids, *, include_blocked=False, top_n=None):
        self.calls.append((job_ids, include_blocked, top_n))
        reports = tuple(item for item in self.reports if item.report.job_id in job_ids)
        return reports if top_n is None else reports[:top_n]


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


def _context() -> CareerAgentContext:
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


def test_rank_to_target_cohort_interrupt_persists_only_runtime_references(tmp_path) -> None:
    ranking = _RankingWorkflow(
        reports=(_stored("mr_2", "job_2"), _stored("mr_1", "job_1"), _stored("mr_3", "job_3")),
        calls=[],
    )
    registry = CareerAgentToolRegistry(
        ranking=ranking,
        target_cohort_gaps=_UnusedWorkflow(),
        job_preparation=_UnusedWorkflow(),
    )
    store = SQLiteCareerAgentCheckpointStore(tmp_path / "agent.sqlite3")
    graph = RankToTargetCohortInterrupt(tool_registry=registry, checkpoints=store)

    result = graph.run(
        context=_context(),
        thread_id="thread_1",
        run_id="run_1",
        request_id="request_1",
        job_ids=("job_3", "job_2", "job_1"),
        top_n=2,
    )

    assert result.status is CareerAgentStatus.INTERRUPTED
    assert result.current_step == "target_cohort_confirmation"
    assert result.ranked_job_ids == ("job_2", "job_1")
    assert result.proposed_target_job_ids == ("job_2", "job_1")
    assert result.current_match_report_ids == ("mr_2", "mr_1")
    assert result.pending_approval is True
    assert result.provider_call_count == 0
    assert result.tool_call_count == 1
    assert ranking.calls == [(('job_3', 'job_2', 'job_1'), False, 2)]

    restored = SQLiteCareerAgentCheckpointStore(tmp_path / "agent.sqlite3").load(
        thread_id="thread_1"
    )
    assert restored == result
    payload = store.load_payload(thread_id="thread_1")
    assert payload is not None
    serialized = str(payload).lower()
    assert "raw_resume" not in serialized
    assert "raw_jd" not in serialized
    assert "api_key" not in serialized


def test_langgraph_rank_to_target_cohort_interrupt_executes_frozen_nodes(tmp_path) -> None:
    ranking = _RankingWorkflow(
        reports=(_stored("mr_2", "job_2"), _stored("mr_1", "job_1")),
        calls=[],
    )
    registry = CareerAgentToolRegistry(
        ranking=ranking,
        target_cohort_gaps=_UnusedWorkflow(),
        job_preparation=_UnusedWorkflow(),
    )
    store = SQLiteCareerAgentCheckpointStore(tmp_path / "agent.sqlite3")
    graph = LangGraphRankToTargetCohortInterrupt(tool_registry=registry, checkpoints=store)

    result = graph.run(
        context=_context(),
        thread_id="thread_langgraph",
        run_id="run_langgraph",
        request_id="request_langgraph",
        job_ids=("job_2", "job_1"),
        top_n=2,
    )

    assert result.status is CareerAgentStatus.INTERRUPTED
    assert result.current_step == "target_cohort_confirmation"
    assert result.ranked_job_ids == ("job_2", "job_1")
    assert result.proposed_target_job_ids == ("job_2", "job_1")
    assert result.current_match_report_ids == ("mr_2", "mr_1")
    assert result.node_count == 2
    assert result.tool_call_count == 1
    assert result.provider_call_count == 0
    assert store.load(thread_id="thread_langgraph") == result


def test_rank_to_target_cohort_interrupt_fails_closed_when_no_current_reports(tmp_path) -> None:
    ranking = _RankingWorkflow(reports=(), calls=[])
    registry = CareerAgentToolRegistry(
        ranking=ranking,
        target_cohort_gaps=_UnusedWorkflow(),
        job_preparation=_UnusedWorkflow(),
    )
    graph = RankToTargetCohortInterrupt(
        tool_registry=registry,
        checkpoints=SQLiteCareerAgentCheckpointStore(tmp_path / "agent.sqlite3"),
    )

    result = graph.run(
        context=_context(),
        thread_id="thread_empty",
        run_id="run_empty",
        request_id="request_empty",
        job_ids=("job_1",),
        top_n=5,
    )

    assert result.status is CareerAgentStatus.BLOCKED
    assert result.current_step == "match_not_ready"
    assert result.pending_approval is False
    assert result.provider_call_count == 0
    assert result.tool_call_count == 1

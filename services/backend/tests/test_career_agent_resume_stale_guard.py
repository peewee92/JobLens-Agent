from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
import hashlib

from app.agent.context import CareerAgentContext, CareerAgentProfileContext
from app.agent.graph.checkpoint import SQLiteCareerAgentCheckpointStore
from app.agent.graph.resume_stale_guard import ResumeStaleGuard
from app.agent.graph.state import CareerAgentState, CareerAgentStatus
from app.agent.tool_registry import CareerAgentToolRegistry
from app.application.match_report.models import MatchRecommendation, MatchReport, StoredMatchReport


@dataclass
class _ContextBuilder:
    context: CareerAgentContext
    calls: int = 0

    def build(self) -> CareerAgentContext:
        self.calls += 1
        return self.context


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


def _resuming_state() -> CareerAgentState:
    report_ids = ("mr_1", "mr_2", "mr_3")
    return CareerAgentState(
        thread_id="thread_1",
        run_id="run_1",
        request_id="request_1",
        status=CareerAgentStatus.RESUMING,
        current_step="target_cohort_resume",
        goal="analyze_target_cohort_gaps",
        profile_id="profile_1",
        profile_version=3,
        requested_job_ids=("job_1", "job_2", "job_3"),
        current_match_report_ids=report_ids,
        match_fingerprint=hashlib.sha256("\n".join(report_ids).encode("utf-8")).hexdigest(),
        ranked_job_ids=("job_1", "job_2", "job_3"),
        proposed_target_job_ids=("job_1", "job_2"),
        confirmed_target_job_ids=("job_3", "job_1"),
        human_decision="edit",
        decision_action_id="action_1",
        tool_call_count=1,
        node_count=2,
    )


def _guard(tmp_path, *, context: CareerAgentContext, reports: tuple[StoredMatchReport, ...]):
    store = SQLiteCareerAgentCheckpointStore(tmp_path / "agent.sqlite3")
    store.save(_resuming_state())
    context_builder = _ContextBuilder(context)
    ranking = _RankingWorkflow(reports=reports, calls=[])
    registry = CareerAgentToolRegistry(
        ranking=ranking,
        target_cohort_gaps=_UnusedWorkflow(),
        job_preparation=_UnusedWorkflow(),
    )
    return ResumeStaleGuard(
        checkpoints=store,
        context_builder=context_builder,
        tool_registry=registry,
    ), store, context_builder, ranking


def test_resume_stale_guard_reloads_current_facts_and_allows_unchanged_snapshot(tmp_path) -> None:
    reports = (_stored("mr_1", "job_1"), _stored("mr_2", "job_2"), _stored("mr_3", "job_3"))
    guard, store, context_builder, ranking = _guard(
        tmp_path,
        context=_context(),
        reports=reports,
    )

    result = guard.validate(thread_id="thread_1")

    assert result.status is CareerAgentStatus.RESUMING
    assert result.current_step == "skill_gap_ready"
    assert result.tool_call_count == 2
    assert result.provider_call_count == 0
    assert context_builder.calls == 1
    assert ranking.calls == [(('job_1', 'job_2', 'job_3'), False, None)]
    assert store.load(thread_id="thread_1") == result


def test_resume_stale_guard_marks_profile_version_change_stale_without_ranking(tmp_path) -> None:
    reports = (_stored("mr_1", "job_1"), _stored("mr_2", "job_2"), _stored("mr_3", "job_3"))
    guard, store, _, ranking = _guard(
        tmp_path,
        context=_context(profile_version=4),
        reports=reports,
    )

    result = guard.validate(thread_id="thread_1")

    assert result.status is CareerAgentStatus.STALE
    assert result.current_step == "resume_stale_profile"
    assert result.tool_call_count == 1
    assert ranking.calls == []
    assert store.load(thread_id="thread_1") == result


def test_resume_stale_guard_marks_match_report_change_stale(tmp_path) -> None:
    reports = (_stored("mr_1", "job_1"), _stored("mr_new", "job_2"), _stored("mr_3", "job_3"))
    guard, store, _, ranking = _guard(tmp_path, context=_context(), reports=reports)

    result = guard.validate(thread_id="thread_1")

    assert result.status is CareerAgentStatus.STALE
    assert result.current_step == "resume_stale_match_reports"
    assert result.tool_call_count == 2
    assert result.provider_call_count == 0
    assert store.load(thread_id="thread_1") == result


def test_resume_stale_guard_is_idempotent_after_validation(tmp_path) -> None:
    reports = (_stored("mr_1", "job_1"), _stored("mr_2", "job_2"), _stored("mr_3", "job_3"))
    guard, _, context_builder, ranking = _guard(tmp_path, context=_context(), reports=reports)

    first = guard.validate(thread_id="thread_1")
    second = guard.validate(thread_id="thread_1")

    assert second == first
    assert context_builder.calls == 1
    assert len(ranking.calls) == 1


def test_resume_stale_guard_fails_closed_when_checkpoint_is_not_resuming(tmp_path) -> None:
    reports = (_stored("mr_1", "job_1"), _stored("mr_2", "job_2"), _stored("mr_3", "job_3"))
    guard, store, _, _ = _guard(tmp_path, context=_context(), reports=reports)
    store.save(replace(_resuming_state(), status=CareerAgentStatus.CANCELLED))

    result = guard.validate(thread_id="thread_1")

    assert result.status is CareerAgentStatus.CANCELLED

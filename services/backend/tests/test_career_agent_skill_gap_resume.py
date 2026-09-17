from __future__ import annotations

from dataclasses import dataclass, replace

from app.agent.context import CareerAgentContext, CareerAgentProfileContext
from app.agent.graph.checkpoint import SQLiteCareerAgentCheckpointStore
from app.agent.graph.skill_gap_resume import SkillGapResumeExecutor
from app.agent.graph.state import CareerAgentState, CareerAgentStatus
from app.agent.tool_registry import CareerAgentToolName, TargetCohortGapsRequest


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


@dataclass(frozen=True)
class _GapResult:
    cohort_id: str
    job_ids: tuple[str, ...]
    facts_usable: bool = True
    blockers: tuple[str, ...] = ()
    provider_calls: int = 0
    db_writes: int = 0


@dataclass
class _Registry:
    calls: list[tuple[CareerAgentToolName, TargetCohortGapsRequest]]

    def invoke(self, *, context, tool, request):
        self.calls.append((tool, request))
        return _GapResult(cohort_id=request.cohort_id, job_ids=request.selected_job_ids)


def _ready_state() -> CareerAgentState:
    return CareerAgentState(
        thread_id="thread_1",
        run_id="run_1",
        request_id="request_1",
        status=CareerAgentStatus.RESUMING,
        current_step="skill_gap_ready",
        goal="analyze_target_cohort_gaps",
        profile_id="profile_1",
        profile_version=3,
        requested_job_ids=("job_1", "job_2", "job_3"),
        ranked_job_ids=("job_1", "job_2", "job_3"),
        proposed_target_job_ids=("job_1", "job_2"),
        confirmed_target_job_ids=("job_3", "job_1"),
        human_decision="edit",
        decision_action_id="action_1",
        tool_call_count=2,
        node_count=3,
    )


def test_skill_gap_resume_executes_confirmed_cohort_once_and_completes(tmp_path) -> None:
    store = SQLiteCareerAgentCheckpointStore(tmp_path / "agent.sqlite3")
    store.save(_ready_state())
    context_builder = _ContextBuilder()
    registry = _Registry(calls=[])
    executor = SkillGapResumeExecutor(
        checkpoints=store,
        context_builder=context_builder,
        tool_registry=registry,  # type: ignore[arg-type]
    )

    first = executor.execute(thread_id="thread_1")
    second = executor.execute(thread_id="thread_1")

    assert first.status is CareerAgentStatus.COMPLETED
    assert first.current_step == "skill_gap_completed"
    assert first.tool_call_count == 3
    assert first.provider_call_count == 0
    assert first.gap_result_fingerprint
    assert second == first
    assert context_builder.calls == 1
    assert len(registry.calls) == 1
    tool, request = registry.calls[0]
    assert tool is CareerAgentToolName.TARGET_COHORT_GAPS
    assert request.selected_job_ids == ("job_3", "job_1")
    assert request.selected_feedback_ids == ()
    assert store.load(thread_id="thread_1") == first


def test_skill_gap_resume_does_nothing_before_stale_guard(tmp_path) -> None:
    store = SQLiteCareerAgentCheckpointStore(tmp_path / "agent.sqlite3")
    store.save(replace(_ready_state(), current_step="target_cohort_resume"))
    context_builder = _ContextBuilder()
    registry = _Registry(calls=[])
    executor = SkillGapResumeExecutor(
        checkpoints=store,
        context_builder=context_builder,
        tool_registry=registry,  # type: ignore[arg-type]
    )

    result = executor.execute(thread_id="thread_1")

    assert result.current_step == "target_cohort_resume"
    assert context_builder.calls == 0
    assert registry.calls == []

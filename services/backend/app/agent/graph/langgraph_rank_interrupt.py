"""LangGraph adapter for the frozen LG-1 Ranking -> Target Cohort interrupt slice.

Business behavior stays in the existing Tool Registry. LangGraph owns only the
explicit state transitions between the read-only ranking node and the durable
interrupt checkpoint node.
"""
from __future__ import annotations

import hashlib
from dataclasses import replace
from typing import Iterable, TypedDict

from langgraph.graph import END, START, StateGraph

from app.application.match_ranking import (
    DEFAULT_TARGET_SUGGESTIONS, MAX_CONFIRMED_TARGETS, MAX_ANALYSIS_JOBS, is_target_candidate, target_suggestion_mode,
)
from app.agent.context import CareerAgentContext
from app.agent.graph.checkpoint_port import CareerAgentCheckpointStore
from app.agent.graph.command_digest import start_command_digest
from app.agent.graph.state import CareerAgentState, CareerAgentStatus
from app.agent.tool_registry import (
    CareerAgentToolName,
    CareerAgentToolRegistry,
    RankMatchReportsRequest,
)


class _GraphState(TypedDict):
    runtime_state: CareerAgentState
    context: CareerAgentContext
    top_n: int
    persisted: bool


class LangGraphRankToTargetCohortInterrupt:
    """Execute the LG-1 pre-HITL slice through a real LangGraph StateGraph."""

    def __init__(
        self,
        *,
        tool_registry: CareerAgentToolRegistry,
        checkpoints: CareerAgentCheckpointStore,
    ) -> None:
        self._tool_registry = tool_registry
        self._checkpoints = checkpoints
        builder = StateGraph(_GraphState)
        builder.add_node("rank_jobs", self._rank_jobs)
        builder.add_node("persist_interrupt", self._persist_interrupt)
        builder.add_edge(START, "rank_jobs")
        builder.add_conditional_edges(
            "rank_jobs",
            self._route_after_ranking,
            {"interrupt": "persist_interrupt", "blocked": END},
        )
        builder.add_edge("persist_interrupt", END)
        self._graph = builder.compile()

    def run(
        self,
        *,
        context: CareerAgentContext,
        thread_id: str,
        run_id: str,
        request_id: str,
        job_ids: tuple[str, ...],
        top_n: int = DEFAULT_TARGET_SUGGESTIONS,
        initial_state: CareerAgentState | None = None,
    ) -> CareerAgentState:
        if not 1 <= top_n <= MAX_CONFIRMED_TARGETS:
            raise ValueError("top_n must be between 1 and 5")
        requested_job_ids = tuple(dict.fromkeys(job_ids))
        if len(requested_job_ids) > MAX_ANALYSIS_JOBS:
            raise ValueError("at most 50 explicit Job IDs are allowed")
        if not requested_job_ids:
            raise ValueError("at least one explicit Job ID is required")

        initial = initial_state or CareerAgentState(
            thread_id=thread_id,
            run_id=run_id,
            request_id=request_id,
            status=CareerAgentStatus.RUNNING,
            current_step="rank_jobs",
            goal="analyze_target_cohort_gaps",
            profile_id=context.profile.id if context.profile is not None else None,
            profile_version=context.profile.version if context.profile is not None else None,
            search_intent_id=(context.search_intent.id if context.search_intent is not None else None),
            search_intent_version=(
                context.search_intent.version if context.search_intent is not None else None
            ),
            requested_job_ids=requested_job_ids,
            requested_top_n=top_n,
            start_command_digest=start_command_digest(
                thread_id=thread_id, run_id=run_id, request_id=request_id,
                job_ids=requested_job_ids, top_n=top_n,
            ),
        )
        if initial_state is not None:
            initial = replace(initial, status=CareerAgentStatus.RUNNING, current_step="rank_jobs")
        result = self._graph.invoke(
            {"runtime_state": initial, "context": context, "top_n": top_n, "persisted": initial_state is not None}
        )
        final = result["runtime_state"]
        return final

    def continue_saved_ranking(self, state: CareerAgentState) -> CareerAgentState:
        """Persist only the waiting point after a previously committed ranking."""
        if state.status is not CareerAgentStatus.RUNNING or state.current_step != "rank_jobs":
            raise ValueError("run has no saved ranking to continue")
        if not state.current_match_report_ids or not state.proposed_target_job_ids:
            raise ValueError("saved ranking has no target proposal")
        return self._persist_interrupt({"runtime_state": state})["runtime_state"]

    def _rank_jobs(self, graph_state: _GraphState) -> dict[str, CareerAgentState]:
        state = graph_state["runtime_state"]
        previous = self._checkpoints.load(thread_id=state.thread_id) if graph_state["persisted"] else None
        check_execution = getattr(self._checkpoints, "assert_execution", None)
        if check_execution:
            check_execution()
        ranked = self._tool_registry.invoke(
            context=graph_state["context"],
            tool=CareerAgentToolName.RANK_MATCH_REPORTS,
            request=RankMatchReportsRequest(
                job_ids=tuple(step.job_id for step in state.update_steps if step.status in {"completed", "reused"})
                    if state.update_steps else state.requested_job_ids,
                include_blocked=False,
                top_n=None,
            ),
        )
        ranked_reports = tuple(ranked) if isinstance(ranked, Iterable) else ()
        report_refs: list[str] = []
        ranked_job_ids: list[str] = []
        suggested_job_ids: list[str] = []
        for item in ranked_reports:
            report_id = getattr(item, "id", None)
            report = getattr(item, "report", None)
            job_id = getattr(report, "job_id", None)
            if isinstance(report_id, str) and isinstance(job_id, str):
                report_refs.append(report_id)
                ranked_job_ids.append(job_id)
                if is_target_candidate(getattr(report, "recommendation", None)):
                    suggested_job_ids.append(job_id)

        # An update must never silently consume reports created after its preflight.
        if state.update_source_thread_id and any(ref not in (
            tuple(step.report_id for step in state.update_steps if step.report_id) if state.update_steps
            else state.update_report_ids) for ref in report_refs):
            stale = self._checkpoints.transition(previous, replace(state, status=CareerAgentStatus.STALE,
                current_step="update_inputs_changed", pending_approval=False))
            return {"runtime_state": stale}

        if not ranked_job_ids:
            blocked = replace(
                state,
                status=CareerAgentStatus.BLOCKED,
                current_step="match_not_ready",
                pending_approval=False,
                tool_call_count=1,
                node_count=1,
            )
            blocked = self._checkpoints.transition(previous, blocked)
            return {"runtime_state": blocked}

        fingerprint = hashlib.sha256("\n".join(report_refs).encode("utf-8")).hexdigest()
        proposed = tuple(dict.fromkeys(suggested_job_ids))[:graph_state["top_n"]]
        ranked_state = replace(
            state,
            current_match_report_ids=tuple(report_refs),
            match_fingerprint=fingerprint,
            ranked_job_ids=tuple(ranked_job_ids),
            proposed_target_job_ids=proposed,
            target_suggestion_mode=target_suggestion_mode(ranked_reports, proposed),
            tool_call_count=1,
            node_count=1,
        )
        if not suggested_job_ids:
            blocked = replace(
                ranked_state, status=CareerAgentStatus.BLOCKED,
                current_step="target_evidence_insufficient", pending_approval=False,
            )
            blocked = self._checkpoints.transition(previous, blocked)
            return {"runtime_state": blocked}
        # LG-3 trace must be produced by real runtime transitions, not inferred
        # later from the final interrupt. Runtime checkpoint/trace writes are
        # explicitly allowed; no business fact is changed here.
        ranked_state = self._checkpoints.transition(previous, ranked_state)
        return {"runtime_state": ranked_state}

    @staticmethod
    def _route_after_ranking(graph_state: _GraphState) -> str:
        state = graph_state["runtime_state"]
        return "blocked" if state.status in {CareerAgentStatus.BLOCKED, CareerAgentStatus.STALE} else "interrupt"

    def _persist_interrupt(self, graph_state: _GraphState) -> dict[str, CareerAgentState]:
        state = graph_state["runtime_state"]
        interrupt_id = "interrupt_" + hashlib.sha256(
            f"{state.thread_id}:{state.run_id}:target_cohort_confirmation".encode("utf-8")
        ).hexdigest()[:24]
        interrupted = replace(
            state,
            status=CareerAgentStatus.INTERRUPTED,
            current_step="target_cohort_confirmation",
            pending_approval=True,
            interrupt_id=interrupt_id,
            node_count=2,
        )
        interrupted = self._checkpoints.transition(state, interrupted)
        return {"runtime_state": interrupted}


__all__ = ["LangGraphRankToTargetCohortInterrupt"]

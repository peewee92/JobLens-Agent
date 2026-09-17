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

from app.agent.context import CareerAgentContext
from app.agent.graph.checkpoint import SQLiteCareerAgentCheckpointStore
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


class LangGraphRankToTargetCohortInterrupt:
    """Execute the LG-1 pre-HITL slice through a real LangGraph StateGraph."""

    def __init__(
        self,
        *,
        tool_registry: CareerAgentToolRegistry,
        checkpoints: SQLiteCareerAgentCheckpointStore,
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
        top_n: int = 5,
    ) -> CareerAgentState:
        if not 1 <= top_n <= 10:
            raise ValueError("top_n must be between 1 and 10")
        requested_job_ids = tuple(dict.fromkeys(job_ids))
        if not requested_job_ids:
            raise ValueError("at least one explicit Job ID is required")

        initial = CareerAgentState(
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
        )
        result = self._graph.invoke(
            {"runtime_state": initial, "context": context, "top_n": top_n}
        )
        final = result["runtime_state"]
        if final.status is CareerAgentStatus.BLOCKED:
            self._checkpoints.save(final)
        return final

    def _rank_jobs(self, graph_state: _GraphState) -> dict[str, CareerAgentState]:
        state = graph_state["runtime_state"]
        ranked = self._tool_registry.invoke(
            context=graph_state["context"],
            tool=CareerAgentToolName.RANK_MATCH_REPORTS,
            request=RankMatchReportsRequest(
                job_ids=state.requested_job_ids,
                include_blocked=False,
                top_n=graph_state["top_n"],
            ),
        )
        ranked_reports = tuple(ranked) if isinstance(ranked, Iterable) else ()
        report_refs: list[str] = []
        ranked_job_ids: list[str] = []
        for item in ranked_reports:
            report_id = getattr(item, "id", None)
            report = getattr(item, "report", None)
            job_id = getattr(report, "job_id", None)
            if isinstance(report_id, str) and isinstance(job_id, str):
                report_refs.append(report_id)
                ranked_job_ids.append(job_id)

        if not ranked_job_ids:
            return {
                "runtime_state": replace(
                    state,
                    status=CareerAgentStatus.BLOCKED,
                    current_step="match_not_ready",
                    pending_approval=False,
                    tool_call_count=1,
                    node_count=1,
                )
            }

        fingerprint = hashlib.sha256("\n".join(report_refs).encode("utf-8")).hexdigest()
        return {
            "runtime_state": replace(
                state,
                current_match_report_ids=tuple(report_refs),
                match_fingerprint=fingerprint,
                ranked_job_ids=tuple(ranked_job_ids),
                proposed_target_job_ids=tuple(ranked_job_ids),
                tool_call_count=1,
                node_count=1,
            )
        }

    @staticmethod
    def _route_after_ranking(graph_state: _GraphState) -> str:
        state = graph_state["runtime_state"]
        return "blocked" if state.status is CareerAgentStatus.BLOCKED else "interrupt"

    def _persist_interrupt(self, graph_state: _GraphState) -> dict[str, CareerAgentState]:
        interrupted = replace(
            graph_state["runtime_state"],
            status=CareerAgentStatus.INTERRUPTED,
            current_step="target_cohort_confirmation",
            pending_approval=True,
            node_count=2,
        )
        self._checkpoints.save(interrupted)
        return {"runtime_state": interrupted}


__all__ = ["LangGraphRankToTargetCohortInterrupt"]

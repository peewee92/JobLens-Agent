"""Deterministic LG-1 slice: Ranking -> Target Cohort proposal -> durable interrupt.

This module deliberately contains no LangGraph dependency yet. It freezes the graph
node contract and persistence semantics first, so the later StateGraph adapter can
remain orchestration-only instead of absorbing Ranking or Target Cohort business
logic.
"""
from __future__ import annotations

import hashlib
from dataclasses import replace
from typing import Iterable

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


class RankToTargetCohortInterrupt:
    """Run the read-only pre-HITL half of the first durable Career Agent graph."""

    def __init__(
        self,
        *,
        tool_registry: CareerAgentToolRegistry,
        checkpoints: CareerAgentCheckpointStore,
    ) -> None:
        self._tool_registry = tool_registry
        self._checkpoints = checkpoints

    def run(
        self,
        *,
        context: CareerAgentContext,
        thread_id: str,
        run_id: str,
        request_id: str,
        job_ids: tuple[str, ...],
        top_n: int = DEFAULT_TARGET_SUGGESTIONS,
    ) -> CareerAgentState:
        if not 1 <= top_n <= MAX_CONFIRMED_TARGETS:
            raise ValueError("top_n must be between 1 and 5")
        requested_job_ids = tuple(dict.fromkeys(job_ids))
        if len(requested_job_ids) > MAX_ANALYSIS_JOBS:
            raise ValueError("at most 50 explicit Job IDs are allowed")
        if not requested_job_ids:
            raise ValueError("at least one explicit Job ID is required")

        state = CareerAgentState(
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

        ranked = self._tool_registry.invoke(
            context=context,
            tool=CareerAgentToolName.RANK_MATCH_REPORTS,
            request=RankMatchReportsRequest(
                job_ids=requested_job_ids,
                include_blocked=False,
                top_n=None,
            ),
        )
        ranked_reports = tuple(ranked) if isinstance(ranked, Iterable) else ()
        state = replace(state, tool_call_count=1, node_count=1)

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

        if not ranked_job_ids:
            blocked = replace(
                state,
                status=CareerAgentStatus.BLOCKED,
                current_step="match_not_ready",
                pending_approval=False,
            )
            return self._checkpoints.transition(None, blocked)

        fingerprint = hashlib.sha256(
            "\n".join(report_refs).encode("utf-8")
        ).hexdigest()
        if not suggested_job_ids:
            blocked = replace(
                state, status=CareerAgentStatus.BLOCKED,
                current_step="target_evidence_insufficient", pending_approval=False,
                ranked_job_ids=tuple(ranked_job_ids), current_match_report_ids=tuple(report_refs),
                match_fingerprint=fingerprint,
            )
            return self._checkpoints.transition(None, blocked)
        interrupt_id = "interrupt_" + hashlib.sha256(
            f"{state.thread_id}:{state.run_id}:target_cohort_confirmation".encode("utf-8")
        ).hexdigest()[:24]
        proposed = tuple(dict.fromkeys(suggested_job_ids))[:top_n]
        interrupted = replace(
            state,
            status=CareerAgentStatus.INTERRUPTED,
            current_step="target_cohort_confirmation",
            current_match_report_ids=tuple(report_refs),
            match_fingerprint=fingerprint,
            ranked_job_ids=tuple(ranked_job_ids),
            proposed_target_job_ids=proposed,
            target_suggestion_mode=target_suggestion_mode(ranked_reports, proposed),
            pending_approval=True,
            interrupt_id=interrupt_id,
            node_count=2,
        )
        return self._checkpoints.transition(None, interrupted)


__all__ = ["RankToTargetCohortInterrupt"]

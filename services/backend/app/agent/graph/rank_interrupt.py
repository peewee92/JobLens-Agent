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

from app.agent.context import CareerAgentContext
from app.agent.graph.checkpoint import SQLiteCareerAgentCheckpointStore
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
        checkpoints: SQLiteCareerAgentCheckpointStore,
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
        top_n: int = 5,
    ) -> CareerAgentState:
        if not 1 <= top_n <= 10:
            raise ValueError("top_n must be between 1 and 10")
        requested_job_ids = tuple(dict.fromkeys(job_ids))
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
        )

        ranked = self._tool_registry.invoke(
            context=context,
            tool=CareerAgentToolName.RANK_MATCH_REPORTS,
            request=RankMatchReportsRequest(
                job_ids=requested_job_ids,
                include_blocked=False,
                top_n=top_n,
            ),
        )
        ranked_reports = tuple(ranked) if isinstance(ranked, Iterable) else ()
        state = replace(state, tool_call_count=1, node_count=1)

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
            blocked = replace(
                state,
                status=CareerAgentStatus.BLOCKED,
                current_step="match_not_ready",
                pending_approval=False,
            )
            self._checkpoints.save(blocked)
            return blocked

        fingerprint = hashlib.sha256(
            "\n".join(report_refs).encode("utf-8")
        ).hexdigest()
        interrupted = replace(
            state,
            status=CareerAgentStatus.INTERRUPTED,
            current_step="target_cohort_confirmation",
            current_match_report_ids=tuple(report_refs),
            match_fingerprint=fingerprint,
            ranked_job_ids=tuple(ranked_job_ids),
            proposed_target_job_ids=tuple(ranked_job_ids),
            pending_approval=True,
            node_count=2,
        )
        self._checkpoints.save(interrupted)
        return interrupted


__all__ = ["RankToTargetCohortInterrupt"]

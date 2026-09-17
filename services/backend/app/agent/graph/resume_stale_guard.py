"""Fail-closed stale validation before a durable Career Agent resume.

LG-2 must never mix an interrupted run's frozen Profile/SearchIntent/MatchReport
identity with newer domain facts. This guard re-reads the governed career context
and current immutable MatchReports before allowing the run to reach Skill Gap.
It performs no Provider calls and no business-state writes.
"""
from __future__ import annotations

import hashlib
from dataclasses import replace
from typing import Iterable, Protocol

from app.agent.context import CareerAgentContext
from app.agent.graph.checkpoint import SQLiteCareerAgentCheckpointStore
from app.agent.graph.state import CareerAgentState, CareerAgentStatus
from app.agent.tool_registry import (
    CareerAgentToolName,
    CareerAgentToolRegistry,
    RankMatchReportsRequest,
)


class CareerAgentContextLoader(Protocol):
    def build(self) -> CareerAgentContext: ...


class ResumeStaleGuard:
    """Validate frozen runtime fact identities exactly once before Gap resume."""

    def __init__(
        self,
        *,
        checkpoints: SQLiteCareerAgentCheckpointStore,
        context_builder: CareerAgentContextLoader,
        tool_registry: CareerAgentToolRegistry,
    ) -> None:
        self._checkpoints = checkpoints
        self._context_builder = context_builder
        self._tool_registry = tool_registry

    def validate(self, *, thread_id: str) -> CareerAgentState:
        state = self._checkpoints.load(thread_id=thread_id)
        if state is None:
            raise ValueError("career agent thread does not exist")

        # Validation is a one-way gate. Replays after VALID/STALE (or any other
        # terminal/non-resuming state) return the persisted result without
        # re-reading facts or re-running a workflow.
        if state.status is not CareerAgentStatus.RESUMING or state.current_step != "target_cohort_resume":
            return state

        context = self._context_builder.build()
        if not context.usable:
            return self._mark_stale(state, step="resume_stale_career_context")

        profile = context.profile
        if (
            profile is None
            or profile.id != state.profile_id
            or profile.version != state.profile_version
        ):
            return self._mark_stale(state, step="resume_stale_profile")

        intent = context.search_intent
        current_intent_id = intent.id if intent is not None else None
        current_intent_version = intent.version if intent is not None else None
        if (
            current_intent_id != state.search_intent_id
            or current_intent_version != state.search_intent_version
        ):
            return self._mark_stale(state, step="resume_stale_search_intent")

        if not state.ranked_job_ids or not state.current_match_report_ids or state.match_fingerprint is None:
            return self._mark_stale(state, step="resume_stale_match_reports")
        if any(job_id not in state.ranked_job_ids for job_id in state.confirmed_target_job_ids):
            # An edited selection is safe only when its MatchReport identity was
            # frozen at interrupt time. LG-1 now snapshots all ranked run jobs.
            return self._mark_stale(state, step="resume_stale_match_reports")

        ranked = self._tool_registry.invoke(
            context=context,
            tool=CareerAgentToolName.RANK_MATCH_REPORTS,
            request=RankMatchReportsRequest(
                job_ids=state.ranked_job_ids,
                include_blocked=False,
                top_n=None,
            ),
        )
        ranked_reports = tuple(ranked) if isinstance(ranked, Iterable) else ()
        current_report_ids: list[str] = []
        current_job_ids: list[str] = []
        for item in ranked_reports:
            report_id = getattr(item, "id", None)
            report = getattr(item, "report", None)
            job_id = getattr(report, "job_id", None)
            if isinstance(report_id, str) and isinstance(job_id, str):
                current_report_ids.append(report_id)
                current_job_ids.append(job_id)

        current_fingerprint = hashlib.sha256(
            "\n".join(current_report_ids).encode("utf-8")
        ).hexdigest()
        if (
            tuple(current_report_ids) != state.current_match_report_ids
            or tuple(current_job_ids) != state.ranked_job_ids
            or current_fingerprint != state.match_fingerprint
        ):
            stale = replace(state, tool_call_count=state.tool_call_count + 1)
            return self._mark_stale(stale, step="resume_stale_match_reports")

        valid = replace(
            state,
            current_step="skill_gap_ready",
            tool_call_count=state.tool_call_count + 1,
            node_count=state.node_count + 1,
        )
        self._checkpoints.save(valid)
        return valid

    def _mark_stale(self, state: CareerAgentState, *, step: str) -> CareerAgentState:
        stale = replace(
            state,
            status=CareerAgentStatus.STALE,
            current_step=step,
            pending_approval=False,
        )
        self._checkpoints.save(stale)
        return stale


__all__ = ["CareerAgentContextLoader", "ResumeStaleGuard"]

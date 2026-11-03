"""Execute the stale-safe confirmed Target Cohort through the existing Gap workflow.

This is the final LG-2 business step. It only consumes a checkpoint that already
passed ResumeStaleGuard, delegates to the existing read-only Skill Gap workflow,
and persists a versioned analysis when the application workflow is configured.
The standalone frozen adapter retains fingerprint-only compatibility. Replays after completion never invoke
the downstream workflow again.
"""
from __future__ import annotations

from dataclasses import is_dataclass, replace
import hashlib
import json
from typing import Protocol

from app.application.saved_career_analysis import (
    BuildSavedCareerAnalysisUseCase, AnalysisFactRequest, AnalysisFactsChangedError,
    AnalysisInputsBlockedError, fact_json,
)
from app.agent.context import CareerAgentContext
from app.agent.graph.checkpoint_port import CareerAgentCheckpointStore
from app.agent.graph.state import CareerAgentState, CareerAgentStatus
from app.agent.tool_registry import (
    CareerAgentToolName,
    CareerAgentToolRegistry,
    TargetCohortGapsRequest,
)


class CareerAgentContextLoader(Protocol):
    def build(self) -> CareerAgentContext: ...


class SkillGapResumeExecutor:
    """Compute confirmed analysis; a failed read-only attempt may be recomputed."""

    def __init__(
        self,
        *,
        checkpoints: CareerAgentCheckpointStore,
        context_builder: CareerAgentContextLoader,
        tool_registry: CareerAgentToolRegistry,
        analysis: BuildSavedCareerAnalysisUseCase | None = None,
    ) -> None:
        self._analysis = analysis
        self._checkpoints = checkpoints
        self._context_builder = context_builder
        self._tool_registry = tool_registry

    def execute(self, *, thread_id: str) -> CareerAgentState:
        state = self._checkpoints.load(thread_id=thread_id)
        if state is None:
            raise ValueError("career agent thread does not exist")

        if state.status is not CareerAgentStatus.RESUMING or state.current_step != "skill_gap_ready":
            return state
        if not state.confirmed_target_job_ids:
            return self._fail(state, step="skill_gap_missing_confirmed_cohort")

        if self._analysis is not None:
            return self._execute_saved_analysis(state)

        context = self._context_builder.build()
        profile = context.profile
        if (
            not context.usable
            or profile is None
            or profile.id != state.profile_id
            or profile.version != state.profile_version
        ):
            return self._stale(state, step="skill_gap_context_changed")

        check_execution = getattr(self._checkpoints, "assert_execution", None)
        if check_execution:
            check_execution()
        result = self._tool_registry.invoke(
            context=context,
            tool=CareerAgentToolName.TARGET_COHORT_GAPS,
            request=TargetCohortGapsRequest(
                cohort_id=f"agent_{state.run_id}",
                name="Career Agent confirmed target cohort",
                selected_job_ids=state.confirmed_target_job_ids,
            ),
        )
        provider_calls = int(getattr(result, "provider_calls", 0) or 0)
        db_writes = int(getattr(result, "db_writes", 0) or 0)
        if provider_calls != 0 or db_writes != 0:
            return self._fail(state, step="skill_gap_forbidden_effect")
        if not bool(getattr(result, "facts_usable", False)):
            return self._fail(state, step="skill_gap_blocked")

        completed = replace(
            state,
            status=CareerAgentStatus.COMPLETED,
            current_step="skill_gap_completed",
            pending_approval=False,
            tool_call_count=state.tool_call_count + 1,
            node_count=state.node_count + 1,
            gap_result_fingerprint=_fingerprint(result),
        )
        return self._checkpoints.transition(state, completed)

    def _execute_saved_analysis(self, state: CareerAgentState) -> CareerAgentState:
        self._checkpoints.assert_execution()
        if any(value is None for value in (state.profile_id, state.profile_version,
            state.search_intent_id, state.search_intent_version)):
            return self._stale(state, step="analysis_facts_changed")
        request = AnalysisFactRequest(profile_id=state.profile_id, profile_version=state.profile_version,
            search_intent_id=state.search_intent_id, search_intent_version=state.search_intent_version,
            match_report_ids=state.current_match_report_ids, selected_job_ids=state.confirmed_target_job_ids)
        try:
            result = self._analysis.execute(thread_id=state.thread_id, run_id=state.run_id, request=request)
        except AnalysisFactsChangedError:
            return self._stale(state, step="analysis_facts_changed")
        except AnalysisInputsBlockedError:
            return self._fail(state, step="analysis_inputs_blocked")
        completed = replace(state, status=CareerAgentStatus.COMPLETED, current_step="skill_gap_completed",
            pending_approval=False, result_id=result.result_id, gap_result_fingerprint=_fingerprint(result.gaps),
            node_count=state.node_count + 1)
        return self._checkpoints.complete_analysis(state, completed, result,
            validate=self._analysis.facts.stale_reasons)

    def _fail(self, state: CareerAgentState, *, step: str) -> CareerAgentState:
        failed = replace(
            state,
            status=CareerAgentStatus.BLOCKED,
            current_step=step,
            pending_approval=False,
        )
        return self._checkpoints.transition(state, failed)

    def _stale(self, state: CareerAgentState, *, step: str) -> CareerAgentState:
        stale = replace(
            state,
            status=CareerAgentStatus.STALE,
            current_step=step,
            pending_approval=False,
        )
        return self._checkpoints.transition(state, stale)


def _fingerprint(result: object) -> str:
    if is_dataclass(result) and not isinstance(result, type):
        payload = fact_json(result)
    else:
        payload = {
            "cohort_id": getattr(result, "cohort_id", None),
            "job_ids": tuple(getattr(result, "job_ids", ()) or ()),
            "facts_usable": getattr(result, "facts_usable", None),
            "blockers": tuple(getattr(result, "blockers", ()) or ()),
        }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


__all__ = ["CareerAgentContextLoader", "SkillGapResumeExecutor"]

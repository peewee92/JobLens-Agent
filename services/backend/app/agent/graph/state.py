"""Explicit, framework-neutral state for the durable Career Agent runtime.

The state deliberately stores only released fact identities, fingerprints, and
runtime control fields. Raw resumes, raw job descriptions, secrets, and large
workflow outputs stay outside control state. Saved analyses are immutable run
results, read by reference rather than regenerated on GET.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any, Literal, Mapping


class CareerAgentStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    INTERRUPTED = "interrupted"
    RESUMING = "resuming"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"
    FAILED = "failed"
    STALE = "stale"


@dataclass(frozen=True, slots=True)
class UpdateMatchStep:
    job_id: str
    extraction_id: str | None
    input_fingerprint: str
    base_report_id: str | None
    status: Literal["pending", "running", "completed", "reused", "failed", "requires_model", "input_blocked"]
    report_id: str | None = None
    attempt: int = 0
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class UpdateBatchCommand:
    action_id: str
    digest: str


@dataclass(frozen=True, slots=True)
class CareerAgentState:
    thread_id: str
    run_id: str
    request_id: str
    status: CareerAgentStatus
    current_step: str
    goal: str
    revision: int = 0
    legacy_read_only: bool = False
    start_command_digest: str | None = None
    requested_top_n: int = 3
    update_source_thread_id: str | None = None
    update_source_result_id: str | None = None
    update_scope: Literal["targets", "batch"] | None = None
    update_input_digest: str | None = None
    update_report_ids: tuple[str, ...] = ()
    update_steps: tuple[UpdateMatchStep, ...] = ()
    update_batch_commands: tuple[UpdateBatchCommand, ...] = ()
    update_partial: bool = False
    update_policy_version: str | None = None
    decision_command_digest: str | None = None
    profile_id: str | None = None
    profile_version: int | None = None
    search_intent_id: str | None = None
    search_intent_version: int | None = None
    requested_job_ids: tuple[str, ...] = ()
    current_match_report_ids: tuple[str, ...] = ()
    match_fingerprint: str | None = None
    ranked_job_ids: tuple[str, ...] = ()
    proposed_target_job_ids: tuple[str, ...] = ()
    target_suggestion_mode: Literal["supported", "challenge_only"] | None = None
    confirmed_target_job_ids: tuple[str, ...] = ()
    pending_approval: bool = False
    interrupt_id: str | None = None
    human_decision: str | None = None
    decision_action_id: str | None = None
    node_count: int = 0
    tool_call_count: int = 0
    provider_call_count: int = 0
    retry_count: int = 0
    last_error_class: str | None = None
    gap_result_fingerprint: str | None = None
    result_id: str | None = None

    def to_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        return payload

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "CareerAgentState":
        values = dict(payload)
        values["status"] = CareerAgentStatus(values["status"])
        for field_name in (
            "requested_job_ids",
            "update_report_ids",
            "current_match_report_ids",
            "ranked_job_ids",
            "proposed_target_job_ids",
            "confirmed_target_job_ids",
        ):
            values[field_name] = tuple(values.get(field_name) or ())
        values["update_steps"] = tuple(UpdateMatchStep(**item) for item in values.get("update_steps", ()))
        values["update_batch_commands"] = tuple(UpdateBatchCommand(**item) for item in values.get("update_batch_commands", ()))
        return cls(**values)


__all__ = ["CareerAgentState", "CareerAgentStatus"]

"""Explicit, framework-neutral state for the durable Career Agent runtime.

The state deliberately stores only released fact identities, fingerprints, and
runtime control fields. Raw resumes, raw job descriptions, secrets, and large
workflow outputs remain in their systems of record and are re-read when needed.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any, Mapping


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
class CareerAgentState:
    thread_id: str
    run_id: str
    request_id: str
    status: CareerAgentStatus
    current_step: str
    goal: str
    profile_id: str | None = None
    profile_version: int | None = None
    search_intent_id: str | None = None
    search_intent_version: int | None = None
    requested_job_ids: tuple[str, ...] = ()
    current_match_report_ids: tuple[str, ...] = ()
    match_fingerprint: str | None = None
    ranked_job_ids: tuple[str, ...] = ()
    proposed_target_job_ids: tuple[str, ...] = ()
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
            "current_match_report_ids",
            "ranked_job_ids",
            "proposed_target_job_ids",
            "confirmed_target_job_ids",
        ):
            values[field_name] = tuple(values.get(field_name) or ())
        return cls(**values)


__all__ = ["CareerAgentState", "CareerAgentStatus"]

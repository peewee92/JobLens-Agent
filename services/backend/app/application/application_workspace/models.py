"""Application Workspace contracts for the vNext 1.2 execution layer."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class ApplicationWorkspaceStatus(StrEnum):
    CONSIDERING = "considering"
    PREPARING = "preparing"
    READY_TO_APPLY = "ready_to_apply"
    APPLIED = "applied"
    INTERVIEWING = "interviewing"
    OFFER = "offer"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class ApplicationTimelineEventType(StrEnum):
    WORKSPACE_CREATED = "workspace_created"
    RESUME_VARIANT_SAVED = "resume_variant_saved"
    ACTION_COMPLETED = "action_completed"
    STATUS_CHANGED = "status_changed"
    MOCK_INTERVIEW_COMPLETED = "mock_interview_completed"
    EVIDENCE_CONFIRMED = "evidence_confirmed"
    REMATCH_COMPLETED = "rematch_completed"
    RANKING_CHANGED = "ranking_changed"


@dataclass(frozen=True, slots=True)
class ApplicationWorkspaceSourceSnapshot:
    profile_id: str
    profile_version: int
    search_intent_id: str
    search_intent_version: int
    requirement_extraction_id: str
    match_report_id: str


@dataclass(frozen=True, slots=True)
class ApplicationTimelineEvent:
    event_id: str
    workspace_id: str
    actor_id: str
    idempotency_key: str
    event_type: ApplicationTimelineEventType
    from_status: ApplicationWorkspaceStatus | None
    to_status: ApplicationWorkspaceStatus | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ApplicationWorkspace:
    workspace_id: str
    job_id: str
    actor_id: str
    idempotency_key: str
    status: ApplicationWorkspaceStatus
    source_snapshot: ApplicationWorkspaceSourceSnapshot
    current_fact_fingerprint: str
    created_at: datetime
    updated_at: datetime

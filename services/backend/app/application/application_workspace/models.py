"""Application Workspace contracts for the vNext 1.2 execution layer."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class ApplicationWorkspaceStatus(StrEnum):
    PREPARING = "preparing"


@dataclass(frozen=True, slots=True)
class ApplicationWorkspaceSourceSnapshot:
    profile_id: str
    profile_version: int
    search_intent_id: str
    search_intent_version: int
    requirement_extraction_id: str
    match_report_id: str


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

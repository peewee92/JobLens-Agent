"""Immutable action origin, separate from the profile a user currently reviews."""
from dataclasses import dataclass
from typing import Protocol
from app.application.application_workspace.models import ApplicationWorkspace
from app.application.application_workspace.execution_action import ExecutionActionItem


@dataclass(frozen=True)
class EvidenceActionSource:
    action_id: str
    profile_id: str
    profile_version: int
    extraction_id: str
    thread_id: str | None
    result_id: str | None
    options: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class EvidenceContext:
    current_profile_id: str | None
    current_profile_version: int | None
    action_sources: tuple[EvidenceActionSource, ...]
    blocked_action_ids: tuple[str, ...]


class EvidenceActionSources(Protocol):
    def resolve(self, action: ExecutionActionItem, workspace: ApplicationWorkspace) -> EvidenceActionSource: ...

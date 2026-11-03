"""Explicit user-controlled Application Status transitions and timeline evidence."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.application.application_workspace.models import (
    ApplicationTimelineEvent,
    ApplicationTimelineEventType,
    ApplicationWorkspace,
    ApplicationWorkspaceStatus,
)


@dataclass(frozen=True, slots=True)
class UpdateApplicationStatusCommand:
    workspace_id: str
    actor_id: str
    idempotency_key: str
    expected_status: ApplicationWorkspaceStatus
    new_status: ApplicationWorkspaceStatus


@dataclass(frozen=True, slots=True)
class ApplicationStatusUpdateResult:
    workspace: ApplicationWorkspace
    event: ApplicationTimelineEvent


class ApplicationStatusBlockedError(RuntimeError):
    """The requested status write cannot safely be applied."""


class WorkspaceStatusRepository(Protocol):
    def get(self, workspace_id: str) -> ApplicationWorkspace | None: ...

    def update_status(
        self,
        *,
        workspace_id: str,
        expected_status: ApplicationWorkspaceStatus,
        new_status: ApplicationWorkspaceStatus,
        updated_at: datetime,
    ) -> ApplicationWorkspace | None: ...


class ApplicationTimelineRepository(Protocol):
    def get_by_actor_and_idempotency_key(
        self, actor_id: str, idempotency_key: str
    ) -> ApplicationTimelineEvent | None: ...

    def add(self, event: ApplicationTimelineEvent) -> ApplicationTimelineEvent: ...


class UpdateApplicationStatusUseCase:
    def __init__(
        self,
        *,
        workspaces: WorkspaceStatusRepository,
        timeline: ApplicationTimelineRepository,
        now: Callable[[], datetime],
        new_event_id: Callable[[], str],
    ) -> None:
        self._workspaces = workspaces
        self._timeline = timeline
        self._now = now
        self._new_event_id = new_event_id

    def execute(self, command: UpdateApplicationStatusCommand) -> ApplicationStatusUpdateResult:
        existing_event = self._timeline.get_by_actor_and_idempotency_key(
            command.actor_id, command.idempotency_key
        )
        if existing_event is not None:
            if (
                existing_event.workspace_id != command.workspace_id
                or existing_event.event_type is not ApplicationTimelineEventType.STATUS_CHANGED
                or existing_event.from_status is not command.expected_status
                or existing_event.to_status is not command.new_status
            ):
                raise ApplicationStatusBlockedError("idempotency_key_conflict")
            workspace = self._workspaces.get(command.workspace_id)
            if workspace is None:
                raise ApplicationStatusBlockedError("application_workspace_not_found")
            return ApplicationStatusUpdateResult(workspace=workspace, event=existing_event)

        workspace = self._workspaces.get(command.workspace_id)
        if workspace is None:
            raise ApplicationStatusBlockedError("application_workspace_not_found")
        if workspace.actor_id != command.actor_id:
            raise ApplicationStatusBlockedError("workspace_actor_mismatch")
        if workspace.status is not command.expected_status:
            raise ApplicationStatusBlockedError("application_status_conflict")
        if command.new_status is command.expected_status:
            raise ApplicationStatusBlockedError("application_status_unchanged")

        changed_at = self._now()
        updated = self._workspaces.update_status(
            workspace_id=command.workspace_id,
            expected_status=command.expected_status,
            new_status=command.new_status,
            updated_at=changed_at,
        )
        if updated is None:
            raise ApplicationStatusBlockedError("application_status_conflict")

        event = self._timeline.add(
            ApplicationTimelineEvent(
                event_id=self._new_event_id(),
                workspace_id=command.workspace_id,
                actor_id=command.actor_id,
                idempotency_key=command.idempotency_key,
                event_type=ApplicationTimelineEventType.STATUS_CHANGED,
                from_status=command.expected_status,
                to_status=command.new_status,
                created_at=changed_at,
            )
        )
        return ApplicationStatusUpdateResult(workspace=updated, event=event)

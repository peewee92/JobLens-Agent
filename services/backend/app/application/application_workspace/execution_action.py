"""Tracked execution actions for a vNext 1.2 Application Workspace."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Callable, Protocol

from app.application.application_workspace.models import ApplicationTimelineEvent, ApplicationTimelineEventType, ApplicationWorkspace
from app.application.job_preparation.bundle import BuildJobPreparationBundleUseCase


class ExecutionActionType(StrEnum):
    LEARN = "learn"
    PRACTICE = "practice"
    COLLECT_EVIDENCE = "collect_evidence"
    IMPROVE_RESUME = "improve_resume"
    PREPARE_INTERVIEW = "prepare_interview"


class ExecutionActionStatus(StrEnum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class ExecutionActionItem:
    action_id: str
    workspace_id: str
    actor_id: str
    idempotency_key: str
    action_type: ExecutionActionType
    status: ExecutionActionStatus
    source_requirement_ids: tuple[str, ...]
    source_gap_capability: str | None
    description: str
    completion_criteria: tuple[str, ...]
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None


class ExecutionActionRepository(Protocol):
    def get(self, action_id: str) -> ExecutionActionItem | None: ...
    def get_by_actor_and_idempotency_key(self, actor_id: str, idempotency_key: str) -> ExecutionActionItem | None: ...
    def list_for_workspace(self, workspace_id: str) -> tuple[ExecutionActionItem, ...]: ...
    def add(self, action: ExecutionActionItem) -> ExecutionActionItem: ...
    def update_status(self, *, action_id: str, expected_status: ExecutionActionStatus, new_status: ExecutionActionStatus, updated_at: datetime, completed_at: datetime | None) -> ExecutionActionItem | None: ...


class WorkspaceRepository(Protocol):
    def get(self, workspace_id: str) -> ApplicationWorkspace | None: ...


class TimelineRepository(Protocol):
    def get_by_actor_and_idempotency_key(self, actor_id: str, idempotency_key: str) -> ApplicationTimelineEvent | None: ...
    def add(self, event: ApplicationTimelineEvent) -> ApplicationTimelineEvent: ...


class ExecutionActionBlockedError(RuntimeError):
    pass


class CreateStudyExecutionActionsUseCase:
    """Materialize grounded Study Checklist items as user-trackable actions."""

    def __init__(self, *, workspaces: WorkspaceRepository, preparation: BuildJobPreparationBundleUseCase, actions: ExecutionActionRepository, now: Callable[[], datetime], new_id: Callable[[], str]) -> None:
        self._workspaces = workspaces
        self._preparation = preparation
        self._actions = actions
        self._now = now
        self._new_id = new_id

    def execute(self, *, workspace_id: str, actor_id: str, idempotency_key: str) -> tuple[ExecutionActionItem, ...]:
        workspace = self._workspaces.get(workspace_id)
        if workspace is None:
            raise ExecutionActionBlockedError("application_workspace_not_found")
        if workspace.actor_id != actor_id:
            raise ExecutionActionBlockedError("application_workspace_actor_mismatch")
        existing = self._actions.get_by_actor_and_idempotency_key(actor_id, idempotency_key)
        if existing is not None:
            if existing.workspace_id != workspace_id:
                raise ExecutionActionBlockedError("execution_action_idempotency_conflict")
            return tuple(action for action in self._actions.list_for_workspace(workspace_id) if action.idempotency_key == idempotency_key or action.idempotency_key.startswith(f"{idempotency_key}:"))

        bundle = self._preparation.execute(workspace.job_id)
        if not bundle.facts_usable or bundle.study_checklist is None:
            raise ExecutionActionBlockedError("study_checklist_not_ready")
        if bundle.profile_id != workspace.source_snapshot.profile_id or bundle.profile_version != workspace.source_snapshot.profile_version or bundle.extraction_id != workspace.source_snapshot.requirement_extraction_id:
            raise ExecutionActionBlockedError("application_workspace_facts_stale")

        created: list[ExecutionActionItem] = []
        now = self._now()
        for index, item in enumerate(bundle.study_checklist.items):
            action_type = ExecutionActionType.COLLECT_EVIDENCE if item.need.value == "add_evidence" else ExecutionActionType.LEARN
            action = ExecutionActionItem(
                action_id=self._new_id(), workspace_id=workspace_id, actor_id=actor_id,
                idempotency_key=idempotency_key if index == 0 else f"{idempotency_key}:{index}", action_type=action_type,
                status=ExecutionActionStatus.TODO, source_requirement_ids=(item.requirement_id,),
                source_gap_capability=item.capability, description=item.requirement_text,
                completion_criteria=item.completion_criteria, created_at=now, updated_at=now,
            )
            created.append(self._actions.add(action))
        return tuple(created)


class UpdateExecutionActionStatusUseCase:
    _allowed = {
        ExecutionActionStatus.TODO: {ExecutionActionStatus.IN_PROGRESS, ExecutionActionStatus.DONE, ExecutionActionStatus.SKIPPED},
        ExecutionActionStatus.IN_PROGRESS: {ExecutionActionStatus.DONE, ExecutionActionStatus.SKIPPED},
        ExecutionActionStatus.DONE: set(),
        ExecutionActionStatus.SKIPPED: set(),
    }

    def __init__(self, *, workspaces: WorkspaceRepository, actions: ExecutionActionRepository, timeline: TimelineRepository, now: Callable[[], datetime], new_event_id: Callable[[], str]) -> None:
        self._workspaces = workspaces
        self._actions = actions
        self._timeline = timeline
        self._now = now
        self._new_event_id = new_event_id

    def execute(self, *, workspace_id: str, action_id: str, actor_id: str, expected_status: ExecutionActionStatus, new_status: ExecutionActionStatus) -> ExecutionActionItem:
        workspace = self._workspaces.get(workspace_id)
        action = self._actions.get(action_id)
        if workspace is None or action is None or action.workspace_id != workspace_id:
            raise ExecutionActionBlockedError("execution_action_not_found")
        if workspace.actor_id != actor_id or action.actor_id != actor_id:
            raise ExecutionActionBlockedError("execution_action_actor_mismatch")
        if action.status != expected_status:
            raise ExecutionActionBlockedError("execution_action_status_conflict")
        if new_status not in self._allowed[expected_status]:
            raise ExecutionActionBlockedError("execution_action_transition_invalid")
        now = self._now()
        updated = self._actions.update_status(action_id=action_id, expected_status=expected_status, new_status=new_status, updated_at=now, completed_at=now if new_status is ExecutionActionStatus.DONE else None)
        if updated is None:
            raise ExecutionActionBlockedError("execution_action_status_conflict")
        if new_status is ExecutionActionStatus.DONE:
            self._ensure_completed_event(updated)
        return updated

    def _ensure_completed_event(self, action: ExecutionActionItem) -> None:
        event_key = f"action-completed:{action.action_id}"
        existing = self._timeline.get_by_actor_and_idempotency_key(action.actor_id, event_key)
        if existing is not None:
            if existing.workspace_id != action.workspace_id or existing.event_type is not ApplicationTimelineEventType.ACTION_COMPLETED:
                raise ExecutionActionBlockedError("execution_action_timeline_conflict")
            return
        self._timeline.add(
            ApplicationTimelineEvent(
                event_id=self._new_event_id(), workspace_id=action.workspace_id, actor_id=action.actor_id,
                idempotency_key=event_key, event_type=ApplicationTimelineEventType.ACTION_COMPLETED,
                from_status=None, to_status=None, created_at=action.completed_at or action.updated_at,
            )
        )

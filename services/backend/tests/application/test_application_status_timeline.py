from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from app.application.application_workspace.models import (
    ApplicationTimelineEventType,
    ApplicationWorkspace,
    ApplicationWorkspaceSourceSnapshot,
    ApplicationWorkspaceStatus,
)
from app.application.application_workspace.status_use_case import (
    ApplicationStatusBlockedError,
    UpdateApplicationStatusCommand,
    UpdateApplicationStatusUseCase,
)

NOW = datetime(2026, 9, 27, tzinfo=timezone.utc)


def _workspace() -> ApplicationWorkspace:
    return ApplicationWorkspace(
        workspace_id="appws_1",
        job_id="job_1",
        actor_id="user_1",
        idempotency_key="create-job-1",
        status=ApplicationWorkspaceStatus.PREPARING,
        source_snapshot=ApplicationWorkspaceSourceSnapshot(
            profile_id="prof_1",
            profile_version=3,
            search_intent_id="intent_1",
            search_intent_version=2,
            requirement_extraction_id="reqrun_1",
            match_report_id="match_1",
        ),
        current_fact_fingerprint="f" * 64,
        created_at=NOW,
        updated_at=NOW,
    )


class WorkspaceRepoStub:
    def __init__(self, workspace: ApplicationWorkspace | None = None) -> None:
        self.workspace = workspace or _workspace()

    def get(self, workspace_id: str) -> ApplicationWorkspace | None:
        return self.workspace if self.workspace.workspace_id == workspace_id else None

    def update_status(
        self,
        *,
        workspace_id: str,
        expected_status: ApplicationWorkspaceStatus,
        new_status: ApplicationWorkspaceStatus,
        updated_at: datetime,
    ) -> ApplicationWorkspace | None:
        if self.workspace.status != expected_status:
            return None
        self.workspace = replace(self.workspace, status=new_status, updated_at=updated_at)
        return self.workspace


class TimelineRepoStub:
    def __init__(self) -> None:
        self.by_idempotency = {}
        self.events = []

    def get_by_actor_and_idempotency_key(self, actor_id: str, idempotency_key: str):
        return self.by_idempotency.get((actor_id, idempotency_key))

    def add(self, event):
        self.events.append(event)
        self.by_idempotency[(event.actor_id, event.idempotency_key)] = event
        return event


def _use_case(*, workspace=None, timeline=None):
    return UpdateApplicationStatusUseCase(
        workspaces=workspace or WorkspaceRepoStub(),
        timeline=timeline or TimelineRepoStub(),
        now=lambda: NOW + timedelta(minutes=5),
        new_event_id=lambda: "appevent_1",
    )


def test_user_status_change_updates_workspace_and_records_timeline_idempotently() -> None:
    workspaces = WorkspaceRepoStub()
    timeline = TimelineRepoStub()
    use_case = _use_case(workspace=workspaces, timeline=timeline)
    command = UpdateApplicationStatusCommand(
        workspace_id="appws_1",
        actor_id="user_1",
        idempotency_key="status-ready-1",
        expected_status=ApplicationWorkspaceStatus.PREPARING,
        new_status=ApplicationWorkspaceStatus.READY_TO_APPLY,
    )

    first = use_case.execute(command)
    second = use_case.execute(command)

    assert first == second
    assert first.workspace.status is ApplicationWorkspaceStatus.READY_TO_APPLY
    assert first.event.event_type is ApplicationTimelineEventType.STATUS_CHANGED
    assert first.event.from_status is ApplicationWorkspaceStatus.PREPARING
    assert first.event.to_status is ApplicationWorkspaceStatus.READY_TO_APPLY
    assert len(timeline.events) == 1


def test_status_change_requires_workspace_owner() -> None:
    with pytest.raises(ApplicationStatusBlockedError, match="workspace_actor_mismatch"):
        _use_case().execute(
            UpdateApplicationStatusCommand(
                workspace_id="appws_1",
                actor_id="user_2",
                idempotency_key="status-ready-1",
                expected_status=ApplicationWorkspaceStatus.PREPARING,
                new_status=ApplicationWorkspaceStatus.READY_TO_APPLY,
            )
        )


def test_status_change_rejects_stale_expected_status() -> None:
    with pytest.raises(ApplicationStatusBlockedError, match="application_status_conflict"):
        _use_case().execute(
            UpdateApplicationStatusCommand(
                workspace_id="appws_1",
                actor_id="user_1",
                idempotency_key="status-ready-1",
                expected_status=ApplicationWorkspaceStatus.CONSIDERING,
                new_status=ApplicationWorkspaceStatus.READY_TO_APPLY,
            )
        )


def test_status_change_rejects_idempotency_key_reuse_for_different_transition() -> None:
    workspaces = WorkspaceRepoStub()
    timeline = TimelineRepoStub()
    use_case = _use_case(workspace=workspaces, timeline=timeline)
    use_case.execute(
        UpdateApplicationStatusCommand(
            workspace_id="appws_1",
            actor_id="user_1",
            idempotency_key="status-1",
            expected_status=ApplicationWorkspaceStatus.PREPARING,
            new_status=ApplicationWorkspaceStatus.READY_TO_APPLY,
        )
    )

    with pytest.raises(ApplicationStatusBlockedError, match="idempotency_key_conflict"):
        use_case.execute(
            UpdateApplicationStatusCommand(
                workspace_id="appws_1",
                actor_id="user_1",
                idempotency_key="status-1",
                expected_status=ApplicationWorkspaceStatus.READY_TO_APPLY,
                new_status=ApplicationWorkspaceStatus.APPLIED,
            )
        )

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.application.application_workspace.execution_action import (
    CreateStudyExecutionActionsUseCase,
    ExecutionActionBlockedError,
    ExecutionActionStatus,
    ExecutionActionType,
    UpdateExecutionActionStatusUseCase,
)
from app.application.application_workspace.models import ApplicationWorkspaceSourceSnapshot
from app.application.job_preparation.study_checklist import StudyChecklistNeed

NOW = datetime(2026, 9, 27, tzinfo=timezone.utc)


class WorkspaceRepo:
    def __init__(self, workspace): self.workspace = workspace
    def get(self, workspace_id): return self.workspace if workspace_id == self.workspace.workspace_id else None


class Preparation:
    def __init__(self, bundle): self.bundle = bundle
    def execute(self, job_id): return self.bundle


class Timeline:
    def __init__(self): self.events = {}
    def get_by_actor_and_idempotency_key(self, actor_id, key): return self.events.get((actor_id, key))
    def add(self, event): self.events[(event.actor_id, event.idempotency_key)] = event; return event


class ActionRepo:
    def __init__(self): self.items = {}
    def get(self, action_id): return self.items.get(action_id)
    def get_by_actor_and_idempotency_key(self, actor_id, key):
        return next((item for item in self.items.values() if item.actor_id == actor_id and item.idempotency_key == key), None)
    def list_for_workspace(self, workspace_id): return tuple(item for item in self.items.values() if item.workspace_id == workspace_id)
    def add(self, action): self.items[action.action_id] = action; return action
    def update_status(self, *, action_id, expected_status, new_status, updated_at, completed_at):
        from dataclasses import replace
        current = self.items.get(action_id)
        if current is None or current.status != expected_status: return None
        updated = replace(current, status=new_status, updated_at=updated_at, completed_at=completed_at)
        self.items[action_id] = updated
        return updated


def _workspace():
    return SimpleNamespace(
        workspace_id="ws_1", job_id="job_1", actor_id="user_1",
        source_snapshot=ApplicationWorkspaceSourceSnapshot("prof_1", 3, "intent_1", 2, "req_1", "match_1"),
    )


def _bundle(profile_version=3):
    items = (
        SimpleNamespace(requirement_id="r1", requirement_text="补充 Python 项目证据", capability="Python", need=StudyChecklistNeed.ADD_EVIDENCE, completion_criteria=("confirmed_evidence_linked_to_skill_exists",)),
        SimpleNamespace(requirement_id="r2", requirement_text="学习 Ray 并形成证据", capability="Ray", need=StudyChecklistNeed.BUILD_CAPABILITY_AND_EVIDENCE, completion_criteria=("confirmed_profile_skill_exists", "confirmed_evidence_linked_to_skill_exists")),
    )
    return SimpleNamespace(job_id="job_1", facts_usable=True, profile_id="prof_1", profile_version=profile_version, extraction_id="req_1", study_checklist=SimpleNamespace(items=items))


def test_create_materializes_grounded_study_actions_and_replays_idempotently():
    repo = ActionRepo()
    ids = iter(("a1", "a2"))
    use_case = CreateStudyExecutionActionsUseCase(workspaces=WorkspaceRepo(_workspace()), preparation=Preparation(_bundle()), actions=repo, now=lambda: NOW, new_id=lambda: next(ids))

    first = use_case.execute(workspace_id="ws_1", actor_id="user_1", idempotency_key="study-1")
    second = use_case.execute(workspace_id="ws_1", actor_id="user_1", idempotency_key="study-1")

    assert first == second
    assert len(repo.items) == 2
    assert first[0].action_type is ExecutionActionType.COLLECT_EVIDENCE
    assert first[1].action_type is ExecutionActionType.LEARN
    assert first[0].source_requirement_ids == ("r1",)


def test_create_fails_closed_when_workspace_snapshot_is_stale():
    use_case = CreateStudyExecutionActionsUseCase(workspaces=WorkspaceRepo(_workspace()), preparation=Preparation(_bundle(profile_version=4)), actions=ActionRepo(), now=lambda: NOW, new_id=lambda: "a1")
    with pytest.raises(ExecutionActionBlockedError, match="application_workspace_facts_stale"):
        use_case.execute(workspace_id="ws_1", actor_id="user_1", idempotency_key="study-1")


def test_done_tracks_action_completion_without_creating_profile_evidence():
    repo = ActionRepo()
    creator = CreateStudyExecutionActionsUseCase(workspaces=WorkspaceRepo(_workspace()), preparation=Preparation(_bundle()), actions=repo, now=lambda: NOW, new_id=iter(("a1", "a2")).__next__)
    action = creator.execute(workspace_id="ws_1", actor_id="user_1", idempotency_key="study-1")[0]
    timeline = Timeline()
    updater = UpdateExecutionActionStatusUseCase(workspaces=WorkspaceRepo(_workspace()), actions=repo, timeline=timeline, now=lambda: NOW, new_event_id=lambda: "evt_1")

    done = updater.execute(workspace_id="ws_1", action_id=action.action_id, actor_id="user_1", expected_status=ExecutionActionStatus.TODO, new_status=ExecutionActionStatus.DONE)

    assert done.status is ExecutionActionStatus.DONE
    event = timeline.events[("user_1", f"action-completed:{action.action_id}")]
    assert event.workspace_id == "ws_1"
    assert event.event_type.value == "action_completed"
    assert done.completed_at == NOW
    assert done.source_requirement_ids == ("r1",)


def test_status_update_rejects_stale_expected_status():
    repo = ActionRepo()
    creator = CreateStudyExecutionActionsUseCase(workspaces=WorkspaceRepo(_workspace()), preparation=Preparation(_bundle()), actions=repo, now=lambda: NOW, new_id=iter(("a1", "a2")).__next__)
    action = creator.execute(workspace_id="ws_1", actor_id="user_1", idempotency_key="study-1")[0]
    updater = UpdateExecutionActionStatusUseCase(workspaces=WorkspaceRepo(_workspace()), actions=repo, timeline=Timeline(), now=lambda: NOW, new_event_id=lambda: "evt_1")
    updater.execute(workspace_id="ws_1", action_id=action.action_id, actor_id="user_1", expected_status=ExecutionActionStatus.TODO, new_status=ExecutionActionStatus.IN_PROGRESS)

    with pytest.raises(ExecutionActionBlockedError, match="execution_action_status_conflict"):
        updater.execute(workspace_id="ws_1", action_id=action.action_id, actor_id="user_1", expected_status=ExecutionActionStatus.TODO, new_status=ExecutionActionStatus.DONE)

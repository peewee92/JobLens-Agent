from datetime import datetime, timezone

import pytest

from app.application.application_workspace.evidence_proposal import CreateEvidenceProposalUseCase, EvidenceProposalBlockedError
from app.application.application_workspace.execution_action import ExecutionActionItem, ExecutionActionStatus, ExecutionActionType
from app.application.application_workspace.models import ApplicationWorkspace, ApplicationWorkspaceSourceSnapshot, ApplicationWorkspaceStatus
from app.domain.career_context import EvidenceType, SkillLevel

NOW = datetime(2026, 9, 27, tzinfo=timezone.utc)


def _workspace():
    return ApplicationWorkspace("ws1", "job1", "user1", "workspace-key", ApplicationWorkspaceStatus.CONSIDERING, ApplicationWorkspaceSourceSnapshot("p1", 3, "s1", 2, "reqx1", "match1"), "f" * 64, NOW, NOW)


def _action(status=ExecutionActionStatus.DONE):
    return ExecutionActionItem("a1", "ws1", "user1", "action-key", ExecutionActionType.COLLECT_EVIDENCE, status, ("req1",), "LangGraph", "补充真实 LangGraph 经历", ("confirmed_evidence_linked_to_skill_exists",), NOW, NOW, NOW if status is ExecutionActionStatus.DONE else None)


class Workspaces:
    def get(self, workspace_id): return _workspace() if workspace_id == "ws1" else None


class Actions:
    def __init__(self, action): self.action = action
    def get(self, action_id): return self.action if action_id == "a1" else None


class Proposals:
    def __init__(self): self.items = []
    def get_by_actor_and_idempotency_key(self, actor_id, key):
        return next((x for x in self.items if x.actor_id == actor_id and x.idempotency_key == key), None)
    def add(self, proposal): self.items.append(proposal); return proposal


def _use_case(action=None):
    repo = Proposals()
    use_case = CreateEvidenceProposalUseCase(workspaces=Workspaces(), actions=Actions(action or _action()), proposals=repo, now=lambda: NOW, new_id=lambda: "ep1")
    return use_case, repo


def test_done_action_creates_user_authored_pending_evidence_proposal_idempotently():
    use_case, repo = _use_case()
    kwargs = dict(workspace_id="ws1", action_id="a1", actor_id="user1", idempotency_key="evidence-key", evidence_type=EvidenceType.PROJECT, evidence_summary="在真实项目中实现 LangGraph checkpoint 恢复链路", evidence_source="JobLens repository", skill_level=SkillLevel.WORKING)
    first = use_case.execute(**kwargs)
    second = use_case.execute(**kwargs)
    assert first == second
    assert first.status.value == "pending_confirmation"
    assert first.source_requirement_ids == ("req1",)
    assert first.source_profile_version == 3
    assert len(repo.items) == 1


def test_action_completion_never_invents_evidence_without_user_fact():
    use_case, _ = _use_case()
    with pytest.raises(EvidenceProposalBlockedError, match="evidence_proposal_fact_required"):
        use_case.execute(workspace_id="ws1", action_id="a1", actor_id="user1", idempotency_key="evidence-key", evidence_type=EvidenceType.PROJECT, evidence_summary=" ", evidence_source=" ", skill_level=SkillLevel.WORKING)


def test_action_must_be_done_before_evidence_proposal():
    use_case, _ = _use_case(_action(ExecutionActionStatus.IN_PROGRESS))
    with pytest.raises(EvidenceProposalBlockedError, match="execution_action_not_done"):
        use_case.execute(workspace_id="ws1", action_id="a1", actor_id="user1", idempotency_key="evidence-key", evidence_type=EvidenceType.PROJECT, evidence_summary="真实经历", evidence_source="repo", skill_level=SkillLevel.WORKING)

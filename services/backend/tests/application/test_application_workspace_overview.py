from __future__ import annotations

from datetime import datetime, timezone

from app.application.application_workspace.models import (
    ApplicationTimelineEvent,
    ApplicationTimelineEventType,
    ApplicationWorkspace,
    ApplicationWorkspaceSourceSnapshot,
    ApplicationWorkspaceStatus,
)
from app.application.application_workspace.overview import BuildApplicationWorkspaceOverviewUseCase
from app.application.application_workspace.execution_action import ExecutionActionStatus
from app.application.application_workspace.evidence_proposal import EvidenceProposalStatus, EvidenceProposal
from app.domain.career_context import EvidenceType, SkillLevel
from app.application.application_workspace.resume_variant import ResumeVariantStatus

NOW = datetime(2026, 9, 27, tzinfo=timezone.utc)


class Repo:
    def __init__(self, value=None, items=()):
        self.value = value
        self.items = items

    def get(self, _id):
        return self.value

    def list_for_workspace(self, _workspace_id):
        return self.items


def workspace():
    return ApplicationWorkspace(
        workspace_id="app_1", job_id="job_1", actor_id="user_1", idempotency_key="k",
        status=ApplicationWorkspaceStatus.PREPARING,
        source_snapshot=ApplicationWorkspaceSourceSnapshot("p", 1, "s", 1, "r", "m"),
        current_fact_fingerprint="f", created_at=NOW, updated_at=NOW,
    )


class Item:
    def __init__(self, status):
        self.status = status


def proposal(status):
    return EvidenceProposal(proposal_id="proposal_1", workspace_id="app_1", action_id="action_1", actor_id="user_1",
        idempotency_key="proposal_1", status=status, source_requirement_ids=("r",), capability="Python",
        evidence_type=EvidenceType.PROJECT, evidence_summary="Actual outcome", evidence_source="Actual repository",
        skill_level=SkillLevel.WORKING, source_profile_id="p", source_profile_version=1, created_at=NOW)


def build(*, variants=(), actions=(), proposals=(), timeline=()):
    return BuildApplicationWorkspaceOverviewUseCase(
        workspaces=Repo(workspace()), variants=Repo(items=variants), actions=Repo(items=actions),
        proposals=Repo(items=proposals), timeline=Repo(items=timeline),
    ).execute("app_1")


def test_next_best_action_prioritizes_resume_review_before_other_preparation():
    result = build()
    assert result.next_best_action.code == "prepare_resume_variant"
    assert result.next_best_action.href == "/applications/app_1#resume"


def test_next_best_action_moves_to_actions_after_reviewed_resume():
    result = build(variants=(Item(ResumeVariantStatus.REVIEWED),))
    assert result.next_best_action.code == "create_execution_actions"


def test_next_best_action_prioritizes_pending_evidence_confirmation():
    result = build(
        variants=(Item(ResumeVariantStatus.REVIEWED),),
        actions=(Item(ExecutionActionStatus.DONE),),
        proposals=(proposal(EvidenceProposalStatus.PENDING_CONFIRMATION),),
    )
    assert result.next_best_action.code == "confirm_evidence"


def test_next_best_action_requests_rematch_after_confirmed_evidence():
    result = build(
        variants=(Item(ResumeVariantStatus.REVIEWED),),
        actions=(Item(ExecutionActionStatus.DONE),),
        proposals=(proposal(EvidenceProposalStatus.CONFIRMED),),
    )
    assert result.next_best_action.code == "rematch"


def test_next_best_action_does_not_repeat_rematch_after_timeline_proves_completion():
    event = ApplicationTimelineEvent(
        event_id="evt", workspace_id="app_1", actor_id="user_1", idempotency_key="e",
        event_type=ApplicationTimelineEventType.REMATCH_COMPLETED, from_status=None, to_status=None, created_at=NOW,
    )
    result = build(
        variants=(Item(ResumeVariantStatus.REVIEWED),),
        actions=(Item(ExecutionActionStatus.DONE),),
        proposals=(proposal(EvidenceProposalStatus.CONFIRMED),),
        timeline=(event,),
    )
    assert result.next_best_action.code == "practice_interview"

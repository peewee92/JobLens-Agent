"""Human-authored Evidence proposals produced from completed execution actions."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Callable, Protocol

from app.application.application_workspace.execution_action import ExecutionActionRepository, ExecutionActionStatus
from app.application.application_workspace.models import ApplicationWorkspace
from app.domain.career_context import EvidenceType, SkillLevel


class EvidenceProposalStatus(StrEnum):
    PENDING_CONFIRMATION = "pending_confirmation"
    CONFIRMED = "confirmed"


@dataclass(frozen=True, slots=True)
class EvidenceProposal:
    proposal_id: str
    workspace_id: str
    action_id: str
    actor_id: str
    idempotency_key: str
    status: EvidenceProposalStatus
    source_requirement_ids: tuple[str, ...]
    capability: str
    evidence_type: EvidenceType
    evidence_summary: str
    evidence_source: str
    skill_level: SkillLevel
    source_profile_id: str
    source_profile_version: int
    created_at: datetime


class WorkspaceRepository(Protocol):
    def get(self, workspace_id: str) -> ApplicationWorkspace | None: ...


class EvidenceProposalRepository(Protocol):
    def get_by_actor_and_idempotency_key(self, actor_id: str, idempotency_key: str) -> EvidenceProposal | None: ...
    def add(self, proposal: EvidenceProposal) -> EvidenceProposal: ...


class EvidenceProposalBlockedError(RuntimeError):
    pass


class CreateEvidenceProposalUseCase:
    """Capture user-authored evidence after an action; never infer career facts from action completion."""

    def __init__(self, *, workspaces: WorkspaceRepository, actions: ExecutionActionRepository, proposals: EvidenceProposalRepository, now: Callable[[], datetime], new_id: Callable[[], str]) -> None:
        self._workspaces = workspaces
        self._actions = actions
        self._proposals = proposals
        self._now = now
        self._new_id = new_id

    def execute(self, *, workspace_id: str, action_id: str, actor_id: str, idempotency_key: str, evidence_type: EvidenceType, evidence_summary: str, evidence_source: str, skill_level: SkillLevel) -> EvidenceProposal:
        workspace = self._workspaces.get(workspace_id)
        action = self._actions.get(action_id)
        if workspace is None or action is None or action.workspace_id != workspace_id:
            raise EvidenceProposalBlockedError("execution_action_not_found")
        if workspace.actor_id != actor_id or action.actor_id != actor_id:
            raise EvidenceProposalBlockedError("evidence_proposal_actor_mismatch")
        if action.status is not ExecutionActionStatus.DONE:
            raise EvidenceProposalBlockedError("execution_action_not_done")
        capability = (action.source_gap_capability or "").strip()
        if not capability or not action.source_requirement_ids:
            raise EvidenceProposalBlockedError("execution_action_not_evidence_grounded")
        summary = evidence_summary.strip()
        source = evidence_source.strip()
        if not summary or not source:
            raise EvidenceProposalBlockedError("evidence_proposal_fact_required")
        existing = self._proposals.get_by_actor_and_idempotency_key(actor_id, idempotency_key)
        if existing is not None:
            if existing.workspace_id != workspace_id or existing.action_id != action_id:
                raise EvidenceProposalBlockedError("evidence_proposal_idempotency_conflict")
            return existing
        proposal = EvidenceProposal(
            proposal_id=self._new_id(), workspace_id=workspace_id, action_id=action_id,
            actor_id=actor_id, idempotency_key=idempotency_key,
            status=EvidenceProposalStatus.PENDING_CONFIRMATION,
            source_requirement_ids=action.source_requirement_ids, capability=capability,
            evidence_type=evidence_type, evidence_summary=summary, evidence_source=source,
            skill_level=skill_level, source_profile_id=workspace.source_snapshot.profile_id,
            source_profile_version=workspace.source_snapshot.profile_version, created_at=self._now(),
        )
        return self._proposals.add(proposal)

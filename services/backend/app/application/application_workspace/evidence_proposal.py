"""Human-authored Evidence proposals produced from completed execution actions."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Callable, Protocol

from app.application.application_workspace.execution_action import ExecutionActionRepository, ExecutionActionStatus
from app.application.application_workspace.models import ApplicationWorkspace
from app.application.career_context.models import EvidenceInput, SaveProfileCommand, SkillInput
from app.application.career_context.use_cases import SaveProfileUseCase
from app.application.ports.career_context_repository import AbstractCareerContextQueryRepository
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
    confirmed_profile_id: str | None = None
    confirmed_profile_version: int | None = None
    confirmed_at: datetime | None = None


class WorkspaceRepository(Protocol):
    def get(self, workspace_id: str) -> ApplicationWorkspace | None: ...


class EvidenceProposalRepository(Protocol):
    def get(self, proposal_id: str) -> EvidenceProposal | None: ...
    def get_by_actor_and_idempotency_key(self, actor_id: str, idempotency_key: str) -> EvidenceProposal | None: ...
    def add(self, proposal: EvidenceProposal) -> EvidenceProposal: ...
    def mark_confirmed(self, *, proposal_id: str, confirmed_profile_id: str, confirmed_profile_version: int, confirmed_at: datetime) -> EvidenceProposal | None: ...


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


class ConfirmEvidenceProposalUseCase:
    """Promote one explicitly confirmed proposal into a new immutable Profile version."""

    def __init__(self, *, workspaces: WorkspaceRepository, proposals: EvidenceProposalRepository, profiles: AbstractCareerContextQueryRepository, save_profile: SaveProfileUseCase, now: Callable[[], datetime]) -> None:
        self._workspaces = workspaces
        self._proposals = proposals
        self._profiles = profiles
        self._save_profile = save_profile
        self._now = now

    def execute(self, *, workspace_id: str, proposal_id: str, actor_id: str) -> EvidenceProposal:
        workspace = self._workspaces.get(workspace_id)
        proposal = self._proposals.get(proposal_id)
        if workspace is None or proposal is None or proposal.workspace_id != workspace_id:
            raise EvidenceProposalBlockedError("evidence_proposal_not_found")
        if workspace.actor_id != actor_id or proposal.actor_id != actor_id:
            raise EvidenceProposalBlockedError("evidence_proposal_actor_mismatch")
        if proposal.status is EvidenceProposalStatus.CONFIRMED:
            return proposal

        current = self._profiles.get_current_profile()
        if current is None or current.id != proposal.source_profile_id or current.version != proposal.source_profile_version:
            raise EvidenceProposalBlockedError("evidence_proposal_profile_stale")

        evidence_key = f"application-action:{proposal.proposal_id}"
        evidence = tuple(EvidenceInput(key=item.key, type=item.type, summary=item.summary, source=item.source) for item in current.evidence) + (
            EvidenceInput(key=evidence_key, type=proposal.evidence_type, summary=proposal.evidence_summary, source=proposal.evidence_source),
        )
        existing_skill = next((item for item in current.skills if item.name.casefold() == proposal.capability.casefold()), None)
        skills = []
        for item in current.skills:
            evidence_keys = tuple(current_evidence.key for current_evidence in current.evidence if current_evidence.id in item.evidence_ids)
            if existing_skill is not None and item.id == existing_skill.id:
                evidence_keys = evidence_keys + (evidence_key,)
                level = proposal.skill_level
            else:
                level = item.level
            skills.append(SkillInput(name=item.name, level=level, evidence_keys=evidence_keys))
        if existing_skill is None:
            skills.append(SkillInput(name=proposal.capability, level=proposal.skill_level, evidence_keys=(evidence_key,)))

        saved = self._save_profile.execute(SaveProfileCommand(
            expected_version=current.version,
            headline=current.headline,
            years_of_experience=current.years_of_experience,
            evidence=evidence,
            skills=tuple(skills),
        ))
        confirmed = self._proposals.mark_confirmed(
            proposal_id=proposal.proposal_id,
            confirmed_profile_id=saved.id,
            confirmed_profile_version=saved.version,
            confirmed_at=self._now(),
        )
        if confirmed is None:
            raise EvidenceProposalBlockedError("evidence_proposal_confirmation_conflict")
        return confirmed

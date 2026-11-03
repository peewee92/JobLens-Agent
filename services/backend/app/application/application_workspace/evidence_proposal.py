"""Human-authored Evidence proposals produced from completed execution actions."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from datetime import datetime
from enum import StrEnum
from typing import Callable, Protocol

from app.application.application_workspace.execution_action import ExecutionActionRepository, ExecutionActionStatus
from app.application.application_workspace.models import (
    ApplicationTimelineEvent,
    ApplicationTimelineEventType,
    ApplicationWorkspace,
)
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
    source_analysis_thread_id: str | None = None
    source_analysis_result_id: str | None = None
    source_requirement_extraction_id: str | None = None
    confirmation_base_profile_id: str | None = None
    confirmation_base_profile_version: int | None = None
    origin_proposal_id: str | None = None
    command_digest: str | None = None


class WorkspaceRepository(Protocol):
    def get(self, workspace_id: str) -> ApplicationWorkspace | None: ...


class EvidenceProposalRepository(Protocol):
    def get(self, proposal_id: str) -> EvidenceProposal | None: ...
    def get_by_actor_and_idempotency_key(self, actor_id: str, idempotency_key: str) -> EvidenceProposal | None: ...
    def list_for_workspace(self, workspace_id: str) -> list[EvidenceProposal]: ...
    def add(self, proposal: EvidenceProposal) -> EvidenceProposal: ...
    def mark_confirmed(self, *, proposal_id: str, confirmed_profile_id: str, confirmed_profile_version: int, confirmed_at: datetime) -> EvidenceProposal | None: ...


class EvidenceConfirmationTimelineRepository(Protocol):
    def get_by_actor_and_idempotency_key(
        self, actor_id: str, idempotency_key: str
    ) -> ApplicationTimelineEvent | None: ...
    def add(self, event: ApplicationTimelineEvent) -> ApplicationTimelineEvent: ...


class EvidenceProposalBlockedError(RuntimeError):
    pass


class CreateEvidenceProposalUseCase:
    """Capture user-authored evidence after an action; never infer career facts from action completion."""

    def __init__(self, *, workspaces: WorkspaceRepository, actions: ExecutionActionRepository, proposals: EvidenceProposalRepository, now: Callable[[], datetime], new_id: Callable[[], str], sources=None, profiles=None) -> None:
        self._workspaces = workspaces
        self._actions = actions
        self._proposals = proposals
        self._now = now
        self._new_id = new_id
        self._sources, self._profiles = sources, profiles

    def execute(self, *, workspace_id: str, action_id: str, actor_id: str, idempotency_key: str, evidence_type: EvidenceType, evidence_summary: str, evidence_source: str, skill_level: SkillLevel, requirement_id: str | None = None,
                expected_profile_id: str | None = None, expected_profile_version: int | None = None,
                reviewed_current_profile: bool = False, origin_proposal_id: str | None = None) -> EvidenceProposal:
        workspace = self._workspaces.get(workspace_id)
        action = self._actions.get(action_id)
        if workspace is None or action is None or action.workspace_id != workspace_id:
            raise EvidenceProposalBlockedError("execution_action_not_found")
        if workspace.actor_id != actor_id or action.actor_id != actor_id:
            raise EvidenceProposalBlockedError("evidence_proposal_actor_mismatch")
        if action.status is not ExecutionActionStatus.DONE:
            raise EvidenceProposalBlockedError("execution_action_not_done")
        summary, source = evidence_summary.strip(), evidence_source.strip()
        if not summary or not source:
            raise EvidenceProposalBlockedError("evidence_proposal_fact_required")
        digest = sha256(json.dumps(dict(workspace=workspace_id, action=action_id, actor=actor_id,
            type=evidence_type.value, summary=summary, source=source, level=skill_level.value,
            requirement=requirement_id, profile=expected_profile_id, version=expected_profile_version,
            reviewed=reviewed_current_profile, origin=origin_proposal_id), sort_keys=True).encode()).hexdigest()
        existing = self._proposals.get_by_actor_and_idempotency_key(actor_id, idempotency_key)
        if existing is not None:
            if existing.command_digest and existing.command_digest != digest:
                raise EvidenceProposalBlockedError("evidence_proposal_idempotency_conflict")
            if (existing.workspace_id, existing.action_id, existing.evidence_type, existing.evidence_summary,
                existing.evidence_source, existing.skill_level, existing.origin_proposal_id) != (
                workspace_id, action_id, evidence_type, summary, source, skill_level, origin_proposal_id):
                raise EvidenceProposalBlockedError("evidence_proposal_idempotency_conflict")
            if requirement_id and existing.source_requirement_ids != (requirement_id,):
                raise EvidenceProposalBlockedError("evidence_proposal_idempotency_conflict")
            if expected_profile_id is not None and (existing.confirmation_base_profile_id,
                existing.confirmation_base_profile_version) != (expected_profile_id, expected_profile_version):
                raise EvidenceProposalBlockedError("evidence_proposal_idempotency_conflict")
            return existing
        action_source = self._sources.resolve(action, workspace) if self._sources else None
        capability = (action.source_gap_capability or "").strip()
        requirement_ids = action.source_requirement_ids
        if requirement_id:
            options = dict(action_source.options) if action_source else {}
            if requirement_id not in options:
                raise EvidenceProposalBlockedError("evidence_proposal_requirement_invalid")
            capability, requirement_ids = options[requirement_id], (requirement_id,)
        elif not capability:
            raise EvidenceProposalBlockedError("evidence_proposal_requirement_required")
        if not capability or not requirement_ids:
            raise EvidenceProposalBlockedError("execution_action_not_evidence_grounded")
        source_profile_id = action_source.profile_id if action_source else workspace.source_snapshot.profile_id
        source_profile_version = action_source.profile_version if action_source else workspace.source_snapshot.profile_version
        base_id, base_version = source_profile_id, source_profile_version
        if expected_profile_id is not None or expected_profile_version is not None:
            current = self._profiles.get_current_profile() if self._profiles else None
            if not reviewed_current_profile:
                raise EvidenceProposalBlockedError("evidence_proposal_review_required")
            if current is None or (current.id, current.version) != (expected_profile_id, expected_profile_version):
                raise EvidenceProposalBlockedError("evidence_proposal_profile_stale")
            base_id, base_version = current.id, current.version
        elif not action.source_gap_capability:
            raise EvidenceProposalBlockedError("evidence_proposal_review_required")
        if origin_proposal_id:
            assert_origin_unconfirmed(self._proposals, workspace_id, origin_proposal_id)
        proposal = EvidenceProposal(
            proposal_id=self._new_id(), workspace_id=workspace_id, action_id=action_id,
            actor_id=actor_id, idempotency_key=idempotency_key,
            status=EvidenceProposalStatus.PENDING_CONFIRMATION,
            source_requirement_ids=requirement_ids, capability=capability,
            evidence_type=evidence_type, evidence_summary=summary, evidence_source=source,
            skill_level=skill_level, source_profile_id=source_profile_id,
            source_profile_version=source_profile_version, created_at=self._now(),
            source_analysis_thread_id=action_source.thread_id if action_source else None,
            source_analysis_result_id=action_source.result_id if action_source else None,
            source_requirement_extraction_id=action_source.extraction_id if action_source else workspace.source_snapshot.requirement_extraction_id,
            confirmation_base_profile_id=base_id, confirmation_base_profile_version=base_version,
            origin_proposal_id=origin_proposal_id, command_digest=digest,
        )
        return self._proposals.add(proposal)


class ConfirmEvidenceProposalUseCase:
    """Promote one explicitly confirmed proposal into a new immutable Profile version."""

    def __init__(self, *, workspaces: WorkspaceRepository, proposals: EvidenceProposalRepository, profiles: AbstractCareerContextQueryRepository, save_profile: SaveProfileUseCase, timeline: EvidenceConfirmationTimelineRepository, now: Callable[[], datetime], new_event_id: Callable[[], str]) -> None:
        self._workspaces = workspaces
        self._proposals = proposals
        self._profiles = profiles
        self._save_profile = save_profile
        self._timeline = timeline
        self._now = now
        self._new_event_id = new_event_id

    def execute(self, *, workspace_id: str, proposal_id: str, actor_id: str) -> EvidenceProposal:
        workspace = self._workspaces.get(workspace_id)
        proposal = self._proposals.get(proposal_id)
        if workspace is None or proposal is None or proposal.workspace_id != workspace_id:
            raise EvidenceProposalBlockedError("evidence_proposal_not_found")
        if workspace.actor_id != actor_id or proposal.actor_id != actor_id:
            raise EvidenceProposalBlockedError("evidence_proposal_actor_mismatch")
        if proposal.status is EvidenceProposalStatus.CONFIRMED:
            self._ensure_confirmation_timeline(proposal)
            return proposal

        current = self._profiles.get_current_profile()
        base_id = proposal.confirmation_base_profile_id or proposal.source_profile_id
        base_version = proposal.confirmation_base_profile_version or proposal.source_profile_version
        if proposal.origin_proposal_id:
            assert_origin_unconfirmed(self._proposals, workspace_id, proposal.origin_proposal_id)
        if current is None or current.id != base_id or current.version != base_version:
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
                level = item.level if proposal.skill_level is SkillLevel.UNKNOWN else proposal.skill_level
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
        self._ensure_confirmation_timeline(confirmed)
        return confirmed

    def _ensure_confirmation_timeline(self, proposal: EvidenceProposal) -> None:
        idempotency_key = f"evidence-confirm:{proposal.proposal_id}"
        existing = self._timeline.get_by_actor_and_idempotency_key(proposal.actor_id, idempotency_key)
        if existing is not None:
            if (
                existing.workspace_id != proposal.workspace_id
                or existing.event_type is not ApplicationTimelineEventType.EVIDENCE_CONFIRMED
            ):
                raise EvidenceProposalBlockedError("evidence_confirmation_timeline_conflict")
            return
        self._timeline.add(ApplicationTimelineEvent(
            event_id=self._new_event_id(),
            workspace_id=proposal.workspace_id,
            actor_id=proposal.actor_id,
            idempotency_key=idempotency_key,
            event_type=ApplicationTimelineEventType.EVIDENCE_CONFIRMED,
            from_status=None,
            to_status=None,
            created_at=proposal.confirmed_at or self._now(),
        ))


def assert_origin_unconfirmed(proposals, workspace_id, origin):
    for item in proposals.list_for_workspace(workspace_id):
        if (item.proposal_id == origin or item.origin_proposal_id == origin) and item.status is EvidenceProposalStatus.CONFIRMED:
            raise EvidenceProposalBlockedError("evidence_proposal_origin_confirmed")


class ReconsiderEvidenceProposalUseCase:
    """Explicit replacement, never a silent rebase or mutation of old user facts."""
    def __init__(self, *, proposals, creator):
        self._proposals, self._creator = proposals, creator

    def execute(self, *, workspace_id, proposal_id, actor_id, idempotency_key,
                expected_profile_id, expected_profile_version, reviewed_current_profile):
        old = self._proposals.get(proposal_id)
        if old is None or old.workspace_id != workspace_id or old.actor_id != actor_id:
            raise EvidenceProposalBlockedError("evidence_proposal_not_found")
        if old.status is not EvidenceProposalStatus.PENDING_CONFIRMATION:
            raise EvidenceProposalBlockedError("evidence_proposal_origin_confirmed")
        return self._creator.execute(workspace_id=workspace_id, action_id=old.action_id, actor_id=actor_id,
            idempotency_key=idempotency_key, evidence_type=old.evidence_type, evidence_summary=old.evidence_summary,
            evidence_source=old.evidence_source, skill_level=old.skill_level,
            requirement_id=old.source_requirement_ids[0] if len(old.source_requirement_ids) == 1 else None,
            expected_profile_id=expected_profile_id, expected_profile_version=expected_profile_version,
            reviewed_current_profile=reviewed_current_profile, origin_proposal_id=old.origin_proposal_id or old.proposal_id)


def pending_evidence_proposals(proposals):
    """Only one actionable pending record per origin; replaced originals remain historical."""
    groups = {}
    for proposal in proposals:
        groups.setdefault(proposal.origin_proposal_id or proposal.proposal_id, []).append(proposal)
    result = []
    for group in groups.values():
        if any(item.status is EvidenceProposalStatus.CONFIRMED for item in group):
            continue
        pending = [item for item in group if item.status is EvidenceProposalStatus.PENDING_CONFIRMATION]
        if pending:
            result.append(max(pending, key=lambda item: (item.created_at, item.proposal_id)))
    return tuple(result)

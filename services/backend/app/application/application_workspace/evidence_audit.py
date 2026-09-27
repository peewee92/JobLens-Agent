"""Read-only audit reconstruction for Evidence Proposal -> confirm -> Profile write."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.application.application_workspace.evidence_proposal import (
    EvidenceProposal,
    EvidenceProposalRepository,
    EvidenceProposalStatus,
)
from app.application.application_workspace.models import (
    ApplicationTimelineEvent,
    ApplicationTimelineEventType,
    ApplicationWorkspace,
)


class WorkspaceRepository(Protocol):
    def get(self, workspace_id: str) -> ApplicationWorkspace | None: ...


class TimelineRepository(Protocol):
    def list_for_workspace(self, workspace_id: str) -> list[ApplicationTimelineEvent]: ...


@dataclass(frozen=True, slots=True)
class EvidenceConfirmationAudit:
    workspace_id: str
    proposal_id: str
    action_id: str
    actor_id: str
    source_requirement_ids: tuple[str, ...]
    source_profile_id: str
    source_profile_version: int
    proposal_recorded: bool
    human_confirmation_recorded: bool
    profile_write_recorded: bool
    confirmed_profile_id: str | None
    confirmed_profile_version: int | None
    confirmation_event_id: str | None
    complete: bool


class EvidenceConfirmationAuditBlockedError(RuntimeError):
    pass


class BuildEvidenceConfirmationAuditUseCase:
    """Reconstruct the persisted proposal -> human confirm -> Profile write chain.

    This is deliberately read-only. It does not infer a successful write from an
    action being done: a complete chain requires both the confirmed proposal's
    immutable Profile identity/version and its unique confirmation Timeline event.
    """

    def __init__(
        self,
        *,
        workspaces: WorkspaceRepository,
        proposals: EvidenceProposalRepository,
        timeline: TimelineRepository,
    ) -> None:
        self._workspaces = workspaces
        self._proposals = proposals
        self._timeline = timeline

    def execute(self, *, workspace_id: str, proposal_id: str) -> EvidenceConfirmationAudit:
        workspace = self._workspaces.get(workspace_id)
        proposal = self._proposals.get(proposal_id)
        if workspace is None or proposal is None or proposal.workspace_id != workspace_id:
            raise EvidenceConfirmationAuditBlockedError("evidence_proposal_not_found")

        confirmation_key = f"evidence-confirm:{proposal.proposal_id}"
        confirmation_events = tuple(
            event
            for event in self._timeline.list_for_workspace(workspace_id)
            if event.actor_id == proposal.actor_id
            and event.idempotency_key == confirmation_key
            and event.event_type is ApplicationTimelineEventType.EVIDENCE_CONFIRMED
        )
        if len(confirmation_events) > 1:
            raise EvidenceConfirmationAuditBlockedError("evidence_confirmation_trace_conflict")
        confirmation_event = confirmation_events[0] if confirmation_events else None

        profile_write_recorded = (
            proposal.status is EvidenceProposalStatus.CONFIRMED
            and proposal.confirmed_profile_id is not None
            and proposal.confirmed_profile_version is not None
            and proposal.confirmed_at is not None
        )
        human_confirmation_recorded = confirmation_event is not None
        if proposal.status is EvidenceProposalStatus.CONFIRMED and (
            not profile_write_recorded or not human_confirmation_recorded
        ):
            raise EvidenceConfirmationAuditBlockedError("evidence_confirmation_trace_incomplete")
        if proposal.status is EvidenceProposalStatus.PENDING_CONFIRMATION and human_confirmation_recorded:
            raise EvidenceConfirmationAuditBlockedError("evidence_confirmation_trace_conflict")

        return EvidenceConfirmationAudit(
            workspace_id=workspace_id,
            proposal_id=proposal.proposal_id,
            action_id=proposal.action_id,
            actor_id=proposal.actor_id,
            source_requirement_ids=proposal.source_requirement_ids,
            source_profile_id=proposal.source_profile_id,
            source_profile_version=proposal.source_profile_version,
            proposal_recorded=True,
            human_confirmation_recorded=human_confirmation_recorded,
            profile_write_recorded=profile_write_recorded,
            confirmed_profile_id=proposal.confirmed_profile_id,
            confirmed_profile_version=proposal.confirmed_profile_version,
            confirmation_event_id=confirmation_event.event_id if confirmation_event else None,
            complete=human_confirmation_recorded and profile_write_recorded,
        )

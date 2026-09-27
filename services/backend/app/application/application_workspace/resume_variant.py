"""Grounded Resume Variant proposal/save contracts for vNext 1.2."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Callable, Protocol

from app.application.application_workspace.models import ApplicationTimelineEventType
from app.application.job_preparation.bundle import BuildJobPreparationBundleUseCase


class ResumeVariantStatus(StrEnum):
    DRAFT = "draft"
    REVIEWED = "reviewed"
    ARCHIVED = "archived"


@dataclass(frozen=True, slots=True)
class ResumeVariantItem:
    requirement_id: str
    capability: str
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ResumeVariantProposal:
    workspace_id: str
    job_id: str
    source_profile_id: str
    source_profile_version: int
    requirement_extraction_id: str
    highlights: tuple[ResumeVariantItem, ...]
    unresolved_requirement_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ResumeVariant:
    variant_id: str
    workspace_id: str
    status: ResumeVariantStatus
    source_profile_id: str
    source_profile_version: int
    requirement_extraction_id: str
    highlights: tuple[ResumeVariantItem, ...]
    created_at: datetime


class ResumeVariantBlockedError(RuntimeError):
    pass


class WorkspaceQuery(Protocol):
    def get(self, workspace_id: str): ...


class ResumeVariantRepository(Protocol):
    def get(self, variant_id: str): ...
    def get_by_actor_and_idempotency_key(self, actor_id: str, idempotency_key: str): ...
    def add(self, *, variant: ResumeVariant, actor_id: str, idempotency_key: str) -> ResumeVariant: ...
    def update_status(self, variant_id: str, *, actor_id: str, status: ResumeVariantStatus) -> ResumeVariant | None: ...


class BuildResumeVariantProposalUseCase:
    def __init__(self, *, workspaces: WorkspaceQuery, preparation: BuildJobPreparationBundleUseCase) -> None:
        self._workspaces = workspaces
        self._preparation = preparation

    def execute(self, workspace_id: str) -> ResumeVariantProposal:
        workspace = self._workspaces.get(workspace_id)
        if workspace is None:
            raise ResumeVariantBlockedError("application_workspace_not_found")
        bundle = self._preparation.execute(workspace.job_id)
        if not bundle.facts_usable or bundle.resume_delta is None:
            raise ResumeVariantBlockedError("resume_facts_not_ready")
        snapshot = workspace.source_snapshot
        if (
            bundle.profile_id != snapshot.profile_id
            or bundle.profile_version != snapshot.profile_version
            or bundle.extraction_id != snapshot.requirement_extraction_id
        ):
            raise ResumeVariantBlockedError("application_workspace_facts_stale")
        highlights = tuple(
            ResumeVariantItem(
                requirement_id=item.requirement_id,
                capability=item.capability,
                evidence_ids=item.evidence_ids,
            )
            for item in bundle.resume_delta.highlights
            if item.evidence_ids
        )
        return ResumeVariantProposal(
            workspace_id=workspace.workspace_id,
            job_id=workspace.job_id,
            source_profile_id=snapshot.profile_id,
            source_profile_version=snapshot.profile_version,
            requirement_extraction_id=snapshot.requirement_extraction_id,
            highlights=highlights,
            unresolved_requirement_ids=tuple(item.requirement_id for item in bundle.resume_delta.evidence_gaps),
        )


class SaveResumeVariantUseCase:
    def __init__(self, *, proposals: BuildResumeVariantProposalUseCase, variants: ResumeVariantRepository, now: Callable[[], datetime], new_id: Callable[[], str]) -> None:
        self._proposals = proposals
        self._variants = variants
        self._now = now
        self._new_id = new_id

    def execute(self, *, workspace_id: str, actor_id: str, idempotency_key: str) -> ResumeVariant:
        existing = self._variants.get_by_actor_and_idempotency_key(actor_id, idempotency_key)
        if existing is not None:
            if existing.workspace_id != workspace_id:
                raise ResumeVariantBlockedError("resume_variant_idempotency_conflict")
            return existing
        proposal = self._proposals.execute(workspace_id)
        if not proposal.highlights:
            raise ResumeVariantBlockedError("resume_variant_has_no_grounded_content")
        variant = ResumeVariant(
            variant_id=self._new_id(),
            workspace_id=workspace_id,
            status=ResumeVariantStatus.DRAFT,
            source_profile_id=proposal.source_profile_id,
            source_profile_version=proposal.source_profile_version,
            requirement_extraction_id=proposal.requirement_extraction_id,
            highlights=proposal.highlights,
            created_at=self._now(),
        )
        return self._variants.add(variant=variant, actor_id=actor_id, idempotency_key=idempotency_key)


class ReviewResumeVariantUseCase:
    """Explicit human review transition; generation/save never self-approves a variant."""

    def __init__(
        self,
        *,
        variants: ResumeVariantRepository,
        proposals: BuildResumeVariantProposalUseCase,
    ) -> None:
        self._variants = variants
        self._proposals = proposals

    def execute(self, *, workspace_id: str, variant_id: str, actor_id: str, expected_status: ResumeVariantStatus) -> ResumeVariant:
        variant = self._variants.get(variant_id)
        if variant is None or variant.workspace_id != workspace_id:
            raise ResumeVariantBlockedError("resume_variant_not_found")
        if variant.status is ResumeVariantStatus.REVIEWED:
            if expected_status not in (ResumeVariantStatus.DRAFT, ResumeVariantStatus.REVIEWED):
                raise ResumeVariantBlockedError("resume_variant_status_conflict")
            owned = self._variants.update_status(variant_id, actor_id=actor_id, status=ResumeVariantStatus.REVIEWED)
            if owned is None:
                raise ResumeVariantBlockedError("resume_variant_actor_mismatch")
            return owned
        if variant.status is not expected_status or variant.status is not ResumeVariantStatus.DRAFT:
            raise ResumeVariantBlockedError("resume_variant_status_conflict")
        current = self._proposals.execute(workspace_id)
        if (
            variant.source_profile_id != current.source_profile_id
            or variant.source_profile_version != current.source_profile_version
            or variant.requirement_extraction_id != current.requirement_extraction_id
        ):
            raise ResumeVariantBlockedError("resume_variant_source_stale")
        if not variant.highlights or any(not item.evidence_ids for item in variant.highlights):
            raise ResumeVariantBlockedError("resume_variant_has_ungrounded_content")
        reviewed = self._variants.update_status(variant_id, actor_id=actor_id, status=ResumeVariantStatus.REVIEWED)
        if reviewed is None:
            raise ResumeVariantBlockedError("resume_variant_actor_mismatch")
        return reviewed

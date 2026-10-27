"""Create a fail-closed Application Workspace from already released facts."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import Callable, Protocol

from app.application.application_workspace.models import (
    ApplicationTimelineEvent,
    ApplicationTimelineEventType,
    ApplicationWorkspace,
    ApplicationWorkspaceSourceSnapshot,
    ApplicationWorkspaceStatus,
)
from app.application.career_context.models import CareerContextSnapshot
from app.application.job_requirements.release import JobRequirementReleaseReadiness
from app.application.match_report.models import StoredMatchReport


@dataclass(frozen=True, slots=True)
class CreateApplicationWorkspaceCommand:
    job_id: str
    actor_id: str
    idempotency_key: str


class ApplicationWorkspaceBlockedError(RuntimeError):
    pass


class CareerContextReader(Protocol):
    def get_current_context(self) -> CareerContextSnapshot: ...


class RequirementGate(Protocol):
    def execute(self, job_id: str) -> JobRequirementReleaseReadiness: ...


class MatchReportReader(Protocol):
    def list_for_job(self, job_id: str) -> tuple[StoredMatchReport, ...]: ...


class WorkspaceRepository(Protocol):
    def get_by_actor_and_idempotency_key(
        self, actor_id: str, idempotency_key: str
    ) -> ApplicationWorkspace | None: ...

    def add(self, workspace: ApplicationWorkspace) -> ApplicationWorkspace: ...


class TimelineRepository(Protocol):
    def get_by_actor_and_idempotency_key(self, actor_id: str, idempotency_key: str) -> ApplicationTimelineEvent | None: ...
    def add(self, event: ApplicationTimelineEvent) -> ApplicationTimelineEvent: ...


class CreateApplicationWorkspaceUseCase:
    def __init__(
        self,
        *,
        career_context: CareerContextReader,
        requirement_gate: RequirementGate,
        match_reports: MatchReportReader,
        workspaces: WorkspaceRepository,
        timeline: TimelineRepository,
        now: Callable[[], datetime],
        new_id: Callable[[], str],
        new_event_id: Callable[[], str],
    ) -> None:
        self._career_context = career_context
        self._requirement_gate = requirement_gate
        self._match_reports = match_reports
        self._workspaces = workspaces
        self._timeline = timeline
        self._now = now
        self._new_id = new_id
        self._new_event_id = new_event_id

    def execute(self, command: CreateApplicationWorkspaceCommand) -> ApplicationWorkspace:
        job_id = command.job_id.strip()
        actor_id = command.actor_id.strip()
        idempotency_key = command.idempotency_key.strip()
        if not job_id or not actor_id or not idempotency_key:
            raise ValueError("job_id, actor_id and idempotency_key are required")

        existing = self._workspaces.get_by_actor_and_idempotency_key(actor_id, idempotency_key)
        if existing is not None:
            if existing.job_id != job_id:
                raise ApplicationWorkspaceBlockedError("idempotency_key_conflict")
            self._ensure_created_event(existing)
            return existing

        context = self._career_context.get_current_context()
        if context.profile is None or context.search_intent is None:
            raise ApplicationWorkspaceBlockedError("career_context_not_ready")

        release = self._requirement_gate.execute(job_id)
        if not release.release_eligible or release.extraction_id is None:
            raise ApplicationWorkspaceBlockedError("requirement_release_not_ready")

        reports = self._match_reports.list_for_job(job_id)
        if not reports:
            raise ApplicationWorkspaceBlockedError("current_match_report_missing")
        current_report = reports[0]
        report = current_report.report
        if (
            report.profile_id != context.profile.id
            or report.profile_version != context.profile.version
            or report.extraction_id != release.extraction_id
        ):
            raise ApplicationWorkspaceBlockedError("current_match_report_stale")

        snapshot = ApplicationWorkspaceSourceSnapshot(
            profile_id=context.profile.id,
            profile_version=context.profile.version,
            search_intent_id=context.search_intent.id,
            search_intent_version=context.search_intent.version,
            requirement_extraction_id=release.extraction_id,
            match_report_id=current_report.id,
        )
        return self.execute_from_snapshot(command, snapshot)

    def execute_from_snapshot(self, command: CreateApplicationWorkspaceCommand,
                              snapshot: ApplicationWorkspaceSourceSnapshot) -> ApplicationWorkspace:
        """Caller owns release/identity validation and transaction for this exact snapshot."""
        job_id, actor_id, idempotency_key = command.job_id, command.actor_id, command.idempotency_key
        if not all((job_id.strip(), actor_id.strip(), idempotency_key.strip())):
            raise ValueError("job_id, actor_id and idempotency_key are required")
        existing = self._workspaces.get_by_actor_and_idempotency_key(actor_id, idempotency_key)
        if existing is not None:
            if existing.job_id != job_id or existing.source_snapshot != snapshot:
                raise ApplicationWorkspaceBlockedError("idempotency_key_conflict")
            self._ensure_created_event(existing)
            return existing
        fingerprint = _fingerprint(job_id, snapshot)
        created_at = self._now()
        workspace = self._workspaces.add(
            ApplicationWorkspace(
                workspace_id=self._new_id(),
                job_id=job_id,
                actor_id=actor_id,
                idempotency_key=idempotency_key,
                status=ApplicationWorkspaceStatus.PREPARING,
                source_snapshot=snapshot,
                current_fact_fingerprint=fingerprint,
                created_at=created_at,
                updated_at=created_at,
            )
        )
        self._ensure_created_event(workspace)
        return workspace

    def _ensure_created_event(self, workspace: ApplicationWorkspace) -> None:
        event_key = f"workspace-created:{workspace.idempotency_key}"
        existing = self._timeline.get_by_actor_and_idempotency_key(workspace.actor_id, event_key)
        if existing is not None:
            if existing.workspace_id != workspace.workspace_id or existing.event_type is not ApplicationTimelineEventType.WORKSPACE_CREATED:
                raise ApplicationWorkspaceBlockedError("timeline_idempotency_conflict")
            return
        self._timeline.add(
            ApplicationTimelineEvent(
                event_id=self._new_event_id(),
                workspace_id=workspace.workspace_id,
                actor_id=workspace.actor_id,
                idempotency_key=event_key,
                event_type=ApplicationTimelineEventType.WORKSPACE_CREATED,
                from_status=None,
                to_status=workspace.status,
                created_at=workspace.created_at,
            )
        )


def _fingerprint(job_id: str, snapshot: ApplicationWorkspaceSourceSnapshot) -> str:
    identity = "|".join(
        (
            job_id,
            snapshot.profile_id,
            str(snapshot.profile_version),
            snapshot.search_intent_id,
            str(snapshot.search_intent_version),
            snapshot.requirement_extraction_id,
            snapshot.match_report_id,
        )
    )
    return sha256(identity.encode("utf-8")).hexdigest()

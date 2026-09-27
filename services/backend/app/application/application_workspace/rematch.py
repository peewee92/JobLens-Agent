"""Explicit zero-provider Re-match after a user-confirmed Evidence proposal."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Callable, Protocol

from app.application.application_workspace.evidence_proposal import EvidenceProposalRepository, EvidenceProposalStatus
from app.application.application_workspace.models import (
    ApplicationTimelineEvent,
    ApplicationTimelineEventType,
    ApplicationWorkspace,
)
from app.application.eligibility import JobEligibilityResult, RequirementFitStatus
from app.application.evidence_retrieval import JobEvidenceRetrievalResult
from app.application.match_improvement import GetMatchImprovementUseCase, MatchImprovement
from app.application.match_report import MatchRecommendation, StoredMatchReport


class WorkspaceRepository(Protocol):
    def get(self, workspace_id: str) -> ApplicationWorkspace | None: ...


class TimelineRepository(Protocol):
    def get_by_actor_and_idempotency_key(self, actor_id: str, idempotency_key: str) -> ApplicationTimelineEvent | None: ...
    def add(self, event: ApplicationTimelineEvent) -> ApplicationTimelineEvent: ...


class MatchReportQuery(Protocol):
    def list_for_job(self, job_id: str) -> tuple[StoredMatchReport, ...]: ...


class EligibilityRunner(Protocol):
    def execute(self, job_id: str) -> JobEligibilityResult: ...


class EvidenceRetrievalRunner(Protocol):
    def execute(self, job_id: str) -> JobEvidenceRetrievalResult: ...


class MatchReportRunner(Protocol):
    def execute(self, job_id: str): ...


class RematchRankingSignal(StrEnum):
    IMPROVED = "improved"
    UNCHANGED = "unchanged"
    WEAKENED = "weakened"


@dataclass(frozen=True, slots=True)
class ApplicationRematchResult:
    workspace_id: str
    proposal_id: str
    previous_match_report_id: str
    current_match_report_id: str
    previous_recommendation: MatchRecommendation
    current_recommendation: MatchRecommendation
    resolved_requirement_ids: tuple[str, ...]
    target_requirement_ids: tuple[str, ...]
    target_resolved_requirement_ids: tuple[str, ...]
    ranking_signal: RematchRankingSignal
    provider_calls: int = 0


class ApplicationRematchBlockedError(RuntimeError):
    pass


_RECOMMENDATION_ORDER = {
    MatchRecommendation.BLOCKED: 0,
    MatchRecommendation.LOW: 1,
    MatchRecommendation.STRETCH: 2,
    MatchRecommendation.GOOD: 3,
    MatchRecommendation.STRONG: 4,
}


class RunApplicationRematchUseCase:
    """Re-match one workspace only when the existing Match pipeline needs zero Provider calls.

    The preflight mirrors SemanticMatchWorkflow's Provider boundary: a non-matched Requirement with
    candidate Evidence requires semantic judgment and is therefore blocked here before any Match
    write. This automation-safe path never converts an unmeasured semantic judgment into a fact.
    """

    def __init__(
        self,
        *,
        workspaces: WorkspaceRepository,
        proposals: EvidenceProposalRepository,
        timeline: TimelineRepository,
        reports: MatchReportQuery,
        eligibility: EligibilityRunner,
        evidence: EvidenceRetrievalRunner,
        report_runner: MatchReportRunner,
        improvement: GetMatchImprovementUseCase,
        now: Callable[[], datetime],
        new_event_id: Callable[[], str],
    ) -> None:
        self._workspaces = workspaces
        self._proposals = proposals
        self._timeline = timeline
        self._reports = reports
        self._eligibility = eligibility
        self._evidence = evidence
        self._report_runner = report_runner
        self._improvement = improvement
        self._now = now
        self._new_event_id = new_event_id

    def execute(self, *, workspace_id: str, proposal_id: str, actor_id: str, idempotency_key: str) -> ApplicationRematchResult:
        workspace = self._workspaces.get(workspace_id)
        proposal = self._proposals.get(proposal_id)
        if workspace is None or proposal is None or proposal.workspace_id != workspace_id:
            raise ApplicationRematchBlockedError("evidence_proposal_not_found")
        if workspace.actor_id != actor_id or proposal.actor_id != actor_id:
            raise ApplicationRematchBlockedError("application_rematch_actor_mismatch")
        if proposal.status is not EvidenceProposalStatus.CONFIRMED or proposal.confirmed_profile_version is None:
            raise ApplicationRematchBlockedError("evidence_proposal_not_confirmed")

        existing_event = self._timeline.get_by_actor_and_idempotency_key(actor_id, idempotency_key)
        if existing_event is not None:
            if existing_event.workspace_id != workspace_id or existing_event.event_type is not ApplicationTimelineEventType.REMATCH_COMPLETED:
                raise ApplicationRematchBlockedError("application_rematch_idempotency_conflict")
            current = self._find_current_report(workspace, proposal.confirmed_profile_version)
            if current is None:
                raise ApplicationRematchBlockedError("application_rematch_result_missing")
            result = self._result(workspace, proposal_id, proposal.source_requirement_ids, current)
            self._ensure_ranking_timeline(result, actor_id=actor_id, idempotency_key=idempotency_key)
            return result

        eligibility = self._eligibility.execute(workspace.job_id)
        if eligibility.profile_version != proposal.confirmed_profile_version:
            raise ApplicationRematchBlockedError("application_rematch_profile_stale")
        evidence = self._evidence.execute(workspace.job_id)
        candidates_by_requirement = {item.requirement_id: item.candidates for item in evidence.requirements}
        provider_required = tuple(
            item.requirement_id
            for item in eligibility.requirements
            if item.status is not RequirementFitStatus.MATCHED and candidates_by_requirement.get(item.requirement_id, ())
        )
        if provider_required:
            raise ApplicationRematchBlockedError("application_rematch_provider_required")

        report = self._report_runner.execute(workspace.job_id)
        if int(getattr(report, "provider_calls", 0)) != 0:
            raise ApplicationRematchBlockedError("application_rematch_provider_budget_violation")
        current = self._find_current_report(workspace, proposal.confirmed_profile_version)
        if current is None:
            raise ApplicationRematchBlockedError("application_rematch_result_missing")
        result = self._result(workspace, proposal_id, proposal.source_requirement_ids, current)
        self._timeline.add(ApplicationTimelineEvent(
            event_id=self._new_event_id(),
            workspace_id=workspace_id,
            actor_id=actor_id,
            idempotency_key=idempotency_key,
            event_type=ApplicationTimelineEventType.REMATCH_COMPLETED,
            from_status=None,
            to_status=None,
            created_at=self._now(),
        ))
        self._ensure_ranking_timeline(result, actor_id=actor_id, idempotency_key=idempotency_key)
        return result

    def _ensure_ranking_timeline(self, result: ApplicationRematchResult, *, actor_id: str, idempotency_key: str) -> None:
        if result.ranking_signal is RematchRankingSignal.UNCHANGED:
            return
        ranking_key = f"{idempotency_key}:ranking"
        existing = self._timeline.get_by_actor_and_idempotency_key(actor_id, ranking_key)
        if existing is not None:
            if (
                existing.workspace_id != result.workspace_id
                or existing.event_type is not ApplicationTimelineEventType.RANKING_CHANGED
            ):
                raise ApplicationRematchBlockedError("application_rematch_ranking_timeline_conflict")
            return
        self._timeline.add(ApplicationTimelineEvent(
            event_id=self._new_event_id(),
            workspace_id=result.workspace_id,
            actor_id=actor_id,
            idempotency_key=ranking_key,
            event_type=ApplicationTimelineEventType.RANKING_CHANGED,
            from_status=None,
            to_status=None,
            created_at=self._now(),
        ))

    def _find_current_report(self, workspace: ApplicationWorkspace, profile_version: int) -> StoredMatchReport | None:
        return next((
            item for item in self._reports.list_for_job(workspace.job_id)
            if item.report.profile_version == profile_version
            and item.report.extraction_id == workspace.source_snapshot.requirement_extraction_id
        ), None)

    def _result(self, workspace: ApplicationWorkspace, proposal_id: str, target_ids: tuple[str, ...], current: StoredMatchReport) -> ApplicationRematchResult:
        improvement: MatchImprovement = self._improvement.execute(job_id=workspace.job_id, current_report_id=current.id)
        if improvement.previous_report_id is None or improvement.previous_recommendation is None:
            raise ApplicationRematchBlockedError("application_rematch_not_comparable")
        previous = improvement.previous_recommendation
        current_recommendation = improvement.current_recommendation
        delta = _RECOMMENDATION_ORDER[current_recommendation] - _RECOMMENDATION_ORDER[previous]
        signal = RematchRankingSignal.IMPROVED if delta > 0 else RematchRankingSignal.WEAKENED if delta < 0 else RematchRankingSignal.UNCHANGED
        target_set = set(target_ids)
        return ApplicationRematchResult(
            workspace_id=workspace.workspace_id,
            proposal_id=proposal_id,
            previous_match_report_id=improvement.previous_report_id,
            current_match_report_id=current.id,
            previous_recommendation=previous,
            current_recommendation=current_recommendation,
            resolved_requirement_ids=improvement.resolved_requirement_ids,
            target_requirement_ids=target_ids,
            target_resolved_requirement_ids=tuple(item for item in improvement.resolved_requirement_ids if item in target_set),
            ranking_signal=signal,
        )

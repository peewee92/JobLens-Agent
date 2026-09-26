from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from app.application.application_workspace.models import ApplicationWorkspace
from app.application.application_workspace.use_case import (
    ApplicationWorkspaceBlockedError,
    CreateApplicationWorkspaceCommand,
    CreateApplicationWorkspaceUseCase,
)
from app.application.career_context.models import (
    CareerContextSnapshot,
    ProfileDetail,
    SearchIntentDetail,
)
from app.application.job_requirements.release import JobRequirementReleaseReadiness
from app.application.match_report.models import MatchRecommendation, StoredMatchReport
from app.application.eligibility import EligibilityDecision

NOW = datetime(2026, 9, 27, tzinfo=timezone.utc)


class CareerContextStub:
    def __init__(self, snapshot: CareerContextSnapshot) -> None:
        self.snapshot = snapshot

    def get_current_context(self) -> CareerContextSnapshot:
        return self.snapshot


class RequirementGateStub:
    def __init__(self, readiness: JobRequirementReleaseReadiness) -> None:
        self.readiness = readiness

    def execute(self, job_id: str) -> JobRequirementReleaseReadiness:
        assert job_id == self.readiness.job_id
        return self.readiness


class MatchReportsStub:
    def __init__(self, report: StoredMatchReport | None) -> None:
        self.report = report

    def list_for_job(self, job_id: str) -> tuple[StoredMatchReport, ...]:
        return (self.report,) if self.report is not None and self.report.report.job_id == job_id else ()


class WorkspaceRepoStub:
    def __init__(self) -> None:
        self.by_idempotency: dict[tuple[str, str], ApplicationWorkspace] = {}
        self.added: list[ApplicationWorkspace] = []

    def get_by_actor_and_idempotency_key(self, actor_id: str, idempotency_key: str):
        return self.by_idempotency.get((actor_id, idempotency_key))

    def add(self, workspace: ApplicationWorkspace) -> ApplicationWorkspace:
        self.added.append(workspace)
        self.by_idempotency[(workspace.actor_id, workspace.idempotency_key)] = workspace
        return workspace


def _profile() -> ProfileDetail:
    return ProfileDetail("prof_1", 3, "AI engineer", 8.0, (), (), NOW)


def _intent() -> SearchIntentDetail:
    return SearchIntentDetail("intent_1", 2, ("AI Engineer",), (), True, None, None, (), (), (), (), NOW)


def _release() -> JobRequirementReleaseReadiness:
    return JobRequirementReleaseReadiness(
        job_id="job_1",
        release_eligible=True,
        current_description_sha256="d" * 64,
        extraction_id="reqrun_1",
        extraction_input_hash="i" * 64,
        provider="fixture",
        model="fixture",
        extractor_version="requirement-extractor-v42.96",
        prompt_version="prompt-v1",
        trace_run_id="run_1",
        requirement_count=3,
        accepted_baseline_batch_id="batch_1",
        accepted_baseline_decision_id="decision_1",
        accepted_baseline_evidence_fingerprint="e" * 64,
        blockers=(),
    )


def _report() -> StoredMatchReport:
    from app.application.match_report.models import MatchReport

    report = MatchReport(
        job_id="job_1",
        profile_id="prof_1",
        profile_version=3,
        extraction_id="reqrun_1",
        eligibility=EligibilityDecision.ELIGIBLE,
        recommendation=MatchRecommendation.STRONG,
        summary="good fit",
        strengths=(),
        risks=(),
        requirement_results=(),
        matched_requirement_ids=(),
        partial_requirement_ids=(),
        missing_requirement_ids=(),
        evidence_links=(),
        matcher_version="matcher-v1",
        prompt_version="prompt-v1",
        model=None,
        trace_run_id=None,
    )
    return StoredMatchReport(id="match_1", report=report, created_at=NOW)


_DEFAULT_REPORT = object()


def _use_case(*, release=None, report=_DEFAULT_REPORT, context=None, repo=None):
    selected_report = _report() if report is _DEFAULT_REPORT else report
    return CreateApplicationWorkspaceUseCase(
        career_context=CareerContextStub(context or CareerContextSnapshot(_profile(), _intent())),
        requirement_gate=RequirementGateStub(release or _release()),
        match_reports=MatchReportsStub(selected_report),
        workspaces=repo or WorkspaceRepoStub(),
        now=lambda: NOW,
        new_id=lambda: "appws_1",
    )


def test_create_freezes_current_fact_snapshot_and_is_idempotent() -> None:
    repo = WorkspaceRepoStub()
    use_case = _use_case(repo=repo)
    command = CreateApplicationWorkspaceCommand(job_id="job_1", actor_id="user_1", idempotency_key="create-job-1")

    first = use_case.execute(command)
    second = use_case.execute(command)

    assert first == second
    assert len(repo.added) == 1
    assert first.source_snapshot.profile_id == "prof_1"
    assert first.source_snapshot.profile_version == 3
    assert first.source_snapshot.search_intent_id == "intent_1"
    assert first.source_snapshot.search_intent_version == 2
    assert first.source_snapshot.requirement_extraction_id == "reqrun_1"
    assert first.source_snapshot.match_report_id == "match_1"
    assert first.current_fact_fingerprint


def test_create_fails_closed_when_requirement_release_is_not_ready() -> None:
    blocked = replace(_release(), release_eligible=False)
    with pytest.raises(ApplicationWorkspaceBlockedError, match="requirement_release_not_ready"):
        _use_case(release=blocked).execute(
            CreateApplicationWorkspaceCommand(job_id="job_1", actor_id="user_1", idempotency_key="k")
        )


def test_create_fails_closed_when_current_match_report_is_missing() -> None:
    with pytest.raises(ApplicationWorkspaceBlockedError, match="current_match_report_missing"):
        _use_case(report=None).execute(
            CreateApplicationWorkspaceCommand(job_id="job_1", actor_id="user_1", idempotency_key="k")
        )


def test_create_rejects_stale_match_report_identity() -> None:
    stale = _report()
    stale = replace(stale, report=replace(stale.report, extraction_id="reqrun_old"))
    with pytest.raises(ApplicationWorkspaceBlockedError, match="current_match_report_stale"):
        _use_case(report=stale).execute(
            CreateApplicationWorkspaceCommand(job_id="job_1", actor_id="user_1", idempotency_key="k")
        )

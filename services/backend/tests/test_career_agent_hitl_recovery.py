from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.agent.context import CareerAgentContext, CareerAgentProfileContext
from app.agent.graph.checkpoint import SQLiteCareerAgentCheckpointStore
from app.agent.graph.hitl_service import CareerAgentHitlService
from app.agent.tool_registry import CareerAgentToolRegistry
from app.api.deps import get_career_agent_hitl_service
from app.application.match_report.models import MatchRecommendation, MatchReport, StoredMatchReport
from app.main import app


@dataclass
class _ContextBuilder:
    profile_version: int = 3

    def build(self) -> CareerAgentContext:
        return CareerAgentContext(
            usable=True,
            confirmation_boundary="confirmed",
            profile=CareerAgentProfileContext(
                id="profile_1",
                version=self.profile_version,
                headline="AI engineer",
                years_of_experience=8,
                skills=(),
            ),
            search_intent=None,
            current_job=None,
            relevant_evidence=(),
            blockers=(),
            blocker_messages=(),
        )


@dataclass
class _RankingWorkflow:
    reports: tuple[StoredMatchReport, ...]

    def execute(self, job_ids, *, include_blocked=False, top_n=None):
        reports = tuple(item for item in self.reports if item.report.job_id in job_ids)
        return reports if top_n is None else reports[:top_n]


@dataclass(frozen=True)
class _GapResult:
    cohort_id: str
    job_ids: tuple[str, ...]
    facts_usable: bool = True
    blockers: tuple[str, ...] = ()
    provider_calls: int = 0
    db_writes: int = 0


@dataclass
class _GapWorkflow:
    calls: int = 0

    def execute(self, command):
        self.calls += 1
        return _GapResult(cohort_id=command.cohort_id, job_ids=command.selected_job_ids)


class _UnusedWorkflow:
    def execute(self, *args, **kwargs):  # pragma: no cover
        raise AssertionError("unrelated workflow must not run")


def _stored(report_id: str, job_id: str) -> StoredMatchReport:
    return StoredMatchReport(
        id=report_id,
        report=MatchReport(
            job_id=job_id,
            profile_id="profile_1",
            profile_version=3,
            extraction_id=f"ext_{job_id}",
            eligibility=None,  # type: ignore[arg-type]
            recommendation=MatchRecommendation.STRONG,
            summary="grounded",
            strengths=(),
            risks=(),
            requirement_results=(),
            matched_requirement_ids=(),
            partial_requirement_ids=(),
            missing_requirement_ids=(),
            evidence_links=(),
            matcher_version="fixture",
            prompt_version="fixture",
            model=None,
            trace_run_id=None,
        ),
        created_at=datetime.now(UTC),
    )


def _service(database_path, context_builder: _ContextBuilder, gaps: _GapWorkflow) -> CareerAgentHitlService:
    ranking = _RankingWorkflow(reports=(_stored("mr_1", "job_1"), _stored("mr_2", "job_2")))
    registry = CareerAgentToolRegistry(
        ranking=ranking,
        target_cohort_gaps=gaps,  # type: ignore[arg-type]
        job_preparation=_UnusedWorkflow(),
    )
    return CareerAgentHitlService(
        checkpoints=SQLiteCareerAgentCheckpointStore(database_path),
        context_builder=context_builder,  # type: ignore[arg-type]
        tool_registry=registry,
    )


def test_http_run_recovers_after_service_recreation_and_stale_resume_fails_closed(tmp_path) -> None:
    database_path = tmp_path / "agent.sqlite3"
    context_builder = _ContextBuilder()
    gaps = _GapWorkflow()

    app.dependency_overrides[get_career_agent_hitl_service] = lambda: _service(
        database_path,
        context_builder,
        gaps,
    )
    try:
        with TestClient(app) as client:
            started = client.post(
                "/api/v1/career-agent/runs",
                json={
                    "threadId": "thread-recovery",
                    "runId": "run-recovery",
                    "requestId": "request-recovery",
                    "jobIds": ["job_1", "job_2"],
                    "topN": 1,
                },
            )
            assert started.status_code == 200
            assert started.json()["status"] == "interrupted"
            interrupt_id = started.json()["interruptId"]

            recovered = client.get("/api/v1/career-agent/runs/thread-recovery")
            assert recovered.status_code == 200
            assert recovered.json()["status"] == "interrupted"
            assert recovered.json()["interruptId"] == interrupt_id

            context_builder.profile_version = 4
            resumed = client.post(
                "/api/v1/career-agent/runs/thread-recovery/resume",
                json={
                    "interruptId": interrupt_id,
                    "actionId": "action-recovery",
                    "decision": "approve",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert resumed.status_code == 200
    assert resumed.json()["status"] == "stale"
    assert resumed.json()["currentStep"] == "resume_stale_profile"
    assert gaps.calls == 0

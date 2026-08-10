"""HTTP contract tests for the read-only Phase 5 Batch Ranking query."""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.api.deps import get_batch_match_ranking_use_case
from app.application.eligibility import EligibilityDecision
from app.application.match_report import MatchRecommendation, MatchReport, StoredMatchReport
from app.main import app


def _stored(report_id: str, job_id: str, recommendation: MatchRecommendation) -> StoredMatchReport:
    return StoredMatchReport(
        id=report_id,
        report=MatchReport(
            job_id=job_id,
            profile_id="profile_1",
            profile_version=1,
            extraction_id=f"reqrun_{job_id}",
            eligibility=(
                EligibilityDecision.BLOCKED
                if recommendation is MatchRecommendation.BLOCKED
                else EligibilityDecision.ELIGIBLE
            ),
            recommendation=recommendation,
            summary="Synthetic API fixture.",
            strengths=(),
            risks=(),
            requirement_results=(),
            matched_requirement_ids=(),
            partial_requirement_ids=(),
            missing_requirement_ids=(),
            evidence_links=(),
            matcher_version="semantic-match-v1",
            prompt_version="semantic-match-v3",
            model="fixture",
            trace_run_id=None,
        ),
        created_at=datetime(2026, 8, 10, tzinfo=UTC),
    )


class _UseCase:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[str, ...], bool]] = []

    def execute(
        self,
        job_ids: tuple[str, ...],
        *,
        include_blocked: bool = False,
    ) -> tuple[StoredMatchReport, ...]:
        self.calls.append((job_ids, include_blocked))
        reports = (
            _stored("report_2", "job_2", MatchRecommendation.STRONG),
            _stored("report_1", "job_1", MatchRecommendation.GOOD),
        )
        if include_blocked:
            return (*reports, _stored("report_3", "job_3", MatchRecommendation.BLOCKED))
        return reports


def test_batch_match_ranking_api_returns_ranked_persisted_snapshots() -> None:
    use_case = _UseCase()
    app.dependency_overrides[get_batch_match_ranking_use_case] = lambda: use_case
    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/match-ranking",
                params=[("jobId", "job_1"), ("jobId", "job_2")],
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert [item["reportId"] for item in body["items"]] == ["report_2", "report_1"]
    assert [item["jobId"] for item in body["items"]] == ["job_2", "job_1"]
    assert [item["recommendation"] for item in body["items"]] == ["strong", "good"]
    assert body["count"] == 2
    assert body["dbWrites"] == 0
    assert body["providerCalls"] == 0
    assert body["traceRunsCreated"] == 0
    assert use_case.calls == [(('job_1', 'job_2'), False)]


def test_batch_match_ranking_api_passes_explicit_include_blocked() -> None:
    use_case = _UseCase()
    app.dependency_overrides[get_batch_match_ranking_use_case] = lambda: use_case
    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/match-ranking",
                params=[("jobId", "job_1"), ("includeBlocked", "true")],
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["items"][-1]["recommendation"] == "blocked"
    assert use_case.calls == [(('job_1',), True)]


def test_batch_match_ranking_api_requires_at_least_one_job_id() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/match-ranking")

    assert response.status_code == 422


def test_openapi_registers_batch_match_ranking_as_read_only_get() -> None:
    with TestClient(app) as client:
        operation = client.get("/openapi.json").json()["paths"]["/api/v1/match-ranking"]["get"]

    assert "requestBody" not in operation
    assert "200" in operation["responses"]
    parameter_names = {item["name"] for item in operation["parameters"]}
    assert parameter_names == {"jobId", "includeBlocked"}

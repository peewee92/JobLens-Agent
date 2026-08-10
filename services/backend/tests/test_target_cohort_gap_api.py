"""HTTP contract tests for transient Target Cohort Gap Detail projection."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.deps import get_target_cohort_gap_query_use_case
from app.application.create_target_cohort import TargetCohortSelectionError
from app.application.target_cohort_gap_detail import (
    BuildTargetCohortGapDetailsResult,
    TargetCohortGapDetail,
)
from app.application.target_cohort_skill_gap_priority import SkillGapPriority
from app.main import app


class _UseCase:
    def __init__(self) -> None:
        self.calls = []

    def execute(self, command):
        self.calls.append(command)
        return BuildTargetCohortGapDetailsResult(
            cohort_id=command.cohort_id,
            job_ids=("job_1", "job_2"),
            facts_usable=True,
            profile_id="profile_1",
            profile_version=3,
            items=(
                TargetCohortGapDetail(
                    capability="FastAPI",
                    priority=SkillGapPriority.P0,
                    why_important={
                        "targetCoverage": 1.0,
                        "mustHaveRatio": 0.5,
                        "gapSeverity": 0.75,
                    },
                    supporting_requirement_ids=("req_1", "req_2"),
                    supporting_job_ids=("job_1", "job_2"),
                    profile_skill_ids=(),
                    evidence_ids=(),
                    current_state="missing",
                    completion_criteria=(
                        "confirmed_profile_skill_exists",
                        "confirmed_evidence_linked_to_skill_exists",
                    ),
                ),
            ),
        )


def test_target_cohort_gap_api_returns_grounded_detail_projection() -> None:
    use_case = _UseCase()
    app.dependency_overrides[get_target_cohort_gap_query_use_case] = lambda: use_case
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/target-cohort/gaps",
                json={
                    "cohortId": "cohort_1",
                    "name": "AI frontend targets",
                    "selectedFeedbackIds": ["feedback_1", "feedback_2"],
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["cohortId"] == "cohort_1"
    assert body["jobIds"] == ["job_1", "job_2"]
    assert body["factsUsable"] is True
    assert body["profileId"] == "profile_1"
    assert body["profileVersion"] == 3
    assert body["items"][0] == {
        "capability": "FastAPI",
        "priority": "P0",
        "whyImportant": {
            "targetCoverage": 1.0,
            "mustHaveRatio": 0.5,
            "gapSeverity": 0.75,
        },
        "supportingRequirementIds": ["req_1", "req_2"],
        "supportingJobIds": ["job_1", "job_2"],
        "profileSkillIds": [],
        "evidenceIds": [],
        "currentState": "missing",
        "completionCriteria": [
            "confirmed_profile_skill_exists",
            "confirmed_evidence_linked_to_skill_exists",
        ],
    }
    assert body["dbWrites"] == 0
    assert body["providerCalls"] == 0
    assert body["traceRunsCreated"] == 0
    assert use_case.calls[0].selected_feedback_ids == ("feedback_1", "feedback_2")


def test_target_cohort_gap_api_returns_conflict_for_stale_feedback_selection() -> None:
    class _StaleSelectionUseCase:
        def execute(self, _command):
            raise TargetCohortSelectionError("feedback 'feedback_old' is not a current cohort candidate")

    app.dependency_overrides[get_target_cohort_gap_query_use_case] = lambda: _StaleSelectionUseCase()
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/target-cohort/gaps",
                json={
                    "cohortId": "cohort_1",
                    "name": "AI frontend targets",
                    "selectedFeedbackIds": ["feedback_old"],
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "target_cohort_selection_invalid"


def test_target_cohort_gap_api_rejects_empty_feedback_selection() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/target-cohort/gaps",
            json={
                "cohortId": "cohort_1",
                "name": "AI frontend targets",
                "selectedFeedbackIds": [],
            },
        )

    assert response.status_code == 422


def test_openapi_registers_target_cohort_gap_post_contract() -> None:
    with TestClient(app) as client:
        operation = client.get("/openapi.json").json()["paths"]["/api/v1/target-cohort/gaps"]["post"]

    assert "requestBody" in operation
    assert "200" in operation["responses"]
    assert "409" in operation["responses"]

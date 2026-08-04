"""HTTP contract tests for the read-only Requirement acceptance dashboard."""
from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_requirement_acceptance_readiness_dashboard_use_case
from app.application.requirement_acceptance.readiness import (
    RequirementAcceptanceReadinessBlocker,
    RequirementAcceptanceReadinessBlockerScope,
    RequirementAcceptanceReadinessNextAction,
    RequirementAcceptanceReadinessResult,
)
from app.application.requirement_acceptance.readiness_dashboard import (
    RequirementAcceptanceDatasetState,
    RequirementAcceptanceReadinessDashboard,
)
from app.main import app


class FakeReadinessUseCase:
    def __init__(self, result: RequirementAcceptanceReadinessDashboard) -> None:
        self.result = result
        self.calls: list[dict[str, object]] = []

    def execute(
        self,
        *,
        reviewer: str,
        title: str | None,
        max_new_extractions: int | None,
    ) -> RequirementAcceptanceReadinessDashboard:
        self.calls.append(
            {
                "reviewer": reviewer,
                "title": title,
                "max_new_extractions": max_new_extractions,
            }
        )
        return self.result


def _blocked_dashboard() -> RequirementAcceptanceReadinessDashboard:
    return RequirementAcceptanceReadinessDashboard(
        dataset_state=RequirementAcceptanceDatasetState.MISSING,
        dataset_candidate_count=0,
        dataset_file_name=None,
        readiness=RequirementAcceptanceReadinessResult(
            dataset_fingerprint=None,
            source_version=None,
            selected_count=0,
            provider="disabled",
            model="",
            api_key_configured=False,
            reviewer="will",
            title="2026-08 acceptance",
            requested_max_new_extractions=1,
            database_reachable=True,
            database_revision="20260804_0013",
            migration_head="20260805_0015",
            workflow_ready=False,
            provider_execution_allowed=False,
            ready_for_next_action=False,
            next_action=RequirementAcceptanceReadinessNextAction.FIX_BLOCKERS,
            run_id=None,
            run_status=None,
            attempted_calls=0,
            canary_decision=None,
            batch_id=None,
            workbench_url=None,
            manual_review_url=None,
            blockers=(
                RequirementAcceptanceReadinessBlocker(
                    scope=RequirementAcceptanceReadinessBlockerScope.WORKFLOW,
                    code="formal_dataset_missing",
                    message="No canonical private dataset is staged.",
                ),
            ),
        ),
    )


@pytest.fixture
def client_and_use_case() -> Iterator[tuple[TestClient, FakeReadinessUseCase]]:
    use_case = FakeReadinessUseCase(_blocked_dashboard())
    app.dependency_overrides[
        get_requirement_acceptance_readiness_dashboard_use_case
    ] = lambda: use_case
    try:
        with TestClient(app) as client:
            yield client, use_case
    finally:
        app.dependency_overrides.clear()


def test_readiness_api_returns_safe_blockers_and_zero_side_effect_evidence(
    client_and_use_case: tuple[TestClient, FakeReadinessUseCase],
) -> None:
    client, use_case = client_and_use_case

    response = client.get(
        "/api/v1/requirement-acceptance-runs/readiness",
        params={
            "reviewer": "will",
            "title": "2026-08 acceptance",
            "max_new_extractions": 1,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["datasetState"] == "missing"
    assert payload["nextAction"] == "fix_blockers"
    assert payload["providerExecutionAllowed"] is False
    assert payload["blockers"] == [
        {
            "scope": "workflow",
            "code": "formal_dataset_missing",
            "message": "No canonical private dataset is staged.",
        }
    ]
    assert payload["dbWrites"] == 0
    assert payload["providerCalls"] == 0
    assert use_case.calls == [
        {
            "reviewer": "will",
            "title": "2026-08 acceptance",
            "max_new_extractions": 1,
        }
    ]
    serialized = response.text
    assert "datasetPath" not in serialized
    assert "recommendedCommand" not in serialized
    assert "OPENAI_API_KEY" not in serialized
    assert "sk-" not in serialized


def test_readiness_api_validates_budget_without_invoking_use_case(
    client_and_use_case: tuple[TestClient, FakeReadinessUseCase],
) -> None:
    client, use_case = client_and_use_case

    response = client.get(
        "/api/v1/requirement-acceptance-runs/readiness",
        params={"max_new_extractions": 21},
    )

    assert response.status_code == 422
    assert use_case.calls == []


def test_openapi_registers_readiness_before_dynamic_run_detail() -> None:
    paths = app.openapi()["paths"]

    assert "/api/v1/requirement-acceptance-runs/readiness" in paths
    assert "get" in paths["/api/v1/requirement-acceptance-runs/readiness"]
    assert "/api/v1/requirement-acceptance-runs/{run_id}" in paths

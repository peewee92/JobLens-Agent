from fastapi.testclient import TestClient

from app.agent.context import CareerAgentContext
from app.agent.entrypoint import CareerAgentGoal, CareerAgentTurnResult
from app.agent.tool_registry import CareerAgentToolName
from app.api.deps import get_career_agent_entrypoint
from app.main import app


class _Entrypoint:
    def execute(self, turn):
        return CareerAgentTurnResult(
            context=CareerAgentContext(
                usable=True,
                confirmation_boundary="confirmed",
                profile=None,
                search_intent=None,
                current_job=None,
                relevant_evidence=(),
                blockers=(),
                blocker_messages=(),
            ),
            goal=turn.goal,
            tool=CareerAgentToolName.RANK_MATCH_REPORTS,
            output={"items": [{"jobId": "job-1"}]},
        )


def test_career_agent_turn_exposes_one_governed_entrypoint() -> None:
    app.dependency_overrides[get_career_agent_entrypoint] = lambda: _Entrypoint()
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/career-agent/turn",
                json={"goal": "rank_jobs", "jobIds": ["job-1"], "topN": 1},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["goal"] == CareerAgentGoal.RANK_JOBS
    assert body["tool"] == CareerAgentToolName.RANK_MATCH_REPORTS
    assert body["output"]["items"][0]["jobId"] == "job-1"


def test_openapi_registers_career_agent_turn_contract() -> None:
    with TestClient(app) as client:
        operation = client.get("/openapi.json").json()["paths"]["/api/v1/career-agent/turn"]["post"]

    assert "200" in operation["responses"]
    assert "422" in operation["responses"]

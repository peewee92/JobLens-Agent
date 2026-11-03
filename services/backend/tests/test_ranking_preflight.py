import json
from pathlib import Path
from unittest.mock import Mock
from sqlalchemy import text

from app.api.v1.schemas.match_ranking import RankingPreflightResponse
from app.workflows.semantic_match import SemanticMatchWorkflow
from .test_career_agent_analysis_snapshot import synthetic_api
from .test_analysis_update_plan import _dump, _profile


def test_real_sqlite_preflight_identifies_missing_and_stale_without_writes_or_model(synthetic_api, monkeypatch):
    client, factory, ids = synthetic_api
    forbidden = Mock(side_effect=AssertionError("preflight must not call a model"))
    monkeypatch.setattr(SemanticMatchWorkflow, "execute", forbidden)
    before = _dump(factory)
    params = [("jobId", ids[0]), ("jobId", "missing_synthetic")]
    response = client.get("/api/v1/match-ranking/preflight", params=params)
    assert response.status_code == 200, response.text
    body = response.json()
    assert [x["jobId"] for x in body["items"]] == [ids[0]]
    assert body["omissions"] == [{"jobId": "missing_synthetic", "reason": "report_missing", "staleReasons": []}]
    assert _dump(factory) == before
    _profile(client)
    before = _dump(factory)
    body = client.get("/api/v1/match-ranking/preflight", params=params).json()
    changed = next(x for x in body["omissions"] if x["jobId"] == ids[0])
    assert changed["reason"] == "report_stale" and "profile_changed" in changed["staleReasons"]
    assert _dump(factory) == before
    forbidden.assert_not_called()


def test_preflight_rejects_duplicate_and_excessive_scope(synthetic_api):
    client, _, ids = synthetic_api
    assert client.get("/api/v1/match-ranking/preflight", params=[("jobId", ids[0]), ("jobId", ids[0])]).status_code == 422
    assert client.get("/api/v1/match-ranking/preflight", params=[("jobId", str(i)) for i in range(51)]).status_code == 422


def test_current_blocked_report_is_distinct_from_missing_and_stale(synthetic_api):
    client, factory, ids = synthetic_api
    with factory.begin() as session:
        session.execute(text("UPDATE match_reports SET recommendation='blocked', eligibility='blocked' WHERE job_id=:id"), {"id": ids[0]})
    before = _dump(factory)
    response = client.get("/api/v1/match-ranking/preflight", params=[("jobId", ids[0])])
    assert response.status_code == 200, response.text
    assert response.json()["omissions"] == [{"jobId": ids[0], "reason": "hard_conflict", "staleReasons": []}]
    assert _dump(factory) == before


def test_preflight_shared_contract_matches_python():
    path = Path(__file__).parents[3] / "packages/contracts/schemas/ranking-preflight.schema.json"
    schema = json.loads(path.read_text())
    del schema["$schema"], schema["$id"]
    assert schema == RankingPreflightResponse.model_json_schema(by_alias=True)

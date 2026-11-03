"""Recent runs are readonly projections of primary runtime records."""
from dataclasses import replace
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.deps import get_career_agent_hitl_service
from app.db.models import CareerAgentRunORM, CareerAgentRunEventORM
from app.main import app
from app.repositories.sqlalchemy_career_agent_checkpoint import SqlAlchemyCareerAgentCheckpointStore as Store
from .test_career_agent_primary_store import _factory
from .test_career_agent_hitl_decision import _interrupted_state
from .test_career_agent_command_integrity import _service
from .test_career_agent_rank_interrupt_graph import _RankingWorkflow


def test_recent_runs_are_bounded_stable_and_do_not_execute_or_create_events(tmp_path):
    factory = _factory(tmp_path)
    store = Store(factory)
    for index in range(12):
        store.transition(None, replace(_interrupted_state(), thread_id=f"thread_{index:02}"))
    with factory() as session, session.begin():
        for row in session.scalars(select(CareerAgentRunORM)):
            row.updated_at = row.created_at + timedelta(seconds=int(row.thread_id[-2:]))
    ranking = _RankingWorkflow((), [])
    app.dependency_overrides[get_career_agent_hitl_service] = lambda: _service(factory, ranking)
    try:
        with TestClient(app) as client:
            result = client.get("/api/v1/career-agent/runs?limit=3")
            assert result.status_code == 200
            items = result.json()["items"]
            assert [item["threadId"] for item in items] == ["thread_11", "thread_10", "thread_09"]
            assert len(client.get("/api/v1/career-agent/runs").json()["items"]) == 10
            for invalid in (0, 21, "bad"):
                assert client.get(f"/api/v1/career-agent/runs?limit={invalid}").status_code == 422
            assert client.get("/api/v1/career-agent/runs/thread_11").json() == items[0]
    finally:
        app.dependency_overrides.pop(get_career_agent_hitl_service, None)
    assert ranking.calls == []
    with factory() as session:
        assert len(session.scalars(select(CareerAgentRunEventORM)).all()) == 12
        assert all(row.lease_token is None for row in session.scalars(select(CareerAgentRunORM)))


def test_recent_runs_tie_breaker_survives_new_store_and_no_legacy_file_is_created(tmp_path):
    factory = _factory(tmp_path)
    store = Store(factory)
    for thread in ("b", "a"):
        store.transition(None, replace(_interrupted_state(), thread_id=thread))
    with factory() as session, session.begin():
        rows = session.scalars(select(CareerAgentRunORM)).all()
        for row in rows:
            row.updated_at = rows[0].created_at
    assert [s.thread_id for s in Store(factory).recent_runs()] == ["b", "a"]

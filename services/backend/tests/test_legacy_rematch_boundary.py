"""Legacy writes are retired regardless of mutable workspace linkage."""
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

import pytest

from app.application.match_report.use_case import BuildJobMatchReportUseCase
from app.db.models import ApplicationWorkspaceORM
from .test_career_agent_analysis_snapshot import synthetic_api
from .test_workspace_feedback_transactions import _setup, _propose
from .test_analysis_update_plan import _dump


@pytest.mark.parametrize("linked", [True, False])
def test_legacy_route_never_writes_even_on_concurrent_replay(synthetic_api, monkeypatch, linked):
    client, factory, ids = synthetic_api
    root, item = _setup(client, factory, ids)
    proposal = _propose(client, root)
    assert client.post(root + f"/evidence-proposals/{proposal['proposalId']}/confirm", json={"actorId": "local-user"}).status_code == 200
    if not linked:
        # Synthetic historical workspace predating saved-analysis references.
        with factory.begin() as session:
            workspace = session.get(ApplicationWorkspaceORM, item["workspaceId"])
            workspace.current_analysis_thread_id = None
            workspace.current_analysis_result_id = None
    forbidden = Mock(side_effect=AssertionError("legacy path must not execute"))
    monkeypatch.setattr(BuildJobMatchReportUseCase, "execute", forbidden)
    before = _dump(factory)
    def request(key):
        return client.post(root + f"/evidence-proposals/{proposal['proposalId']}/rematch", json={"actorId": "local-user", "idempotencyKey": key})
    with ThreadPoolExecutor(max_workers=3) as pool:
        responses = list(pool.map(request, ["same", "same", "other"]))
    assert all(response.status_code == 410 and response.json()["detail"] == "application_rematch_retired" for response in responses)
    assert _dump(factory) == before
    forbidden.assert_not_called()

"""Real SQLite and actual HTTP workflow: saved result -> atomic workspace preparation."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from sqlalchemy import select, text, func

from app.application.job_preparation.bundle import BuildJobPreparationBundleUseCase
from app.db.models import (
    ApplicationWorkspaceORM, ResumeVariantORM, ExecutionActionItemORM,
    ApplicationTimelineEventORM, AnalysisExecutionReceiptORM, UserProfileORM,
)
from .test_career_agent_analysis_snapshot import synthetic_api, start, approve


def _completed(client, ids, thread="execution"):
    state = start(client, ids, thread)
    response = approve(client, state)
    assert response.status_code == 200, response.text
    completed = response.json()
    assert completed["status"] == "completed"
    return {"commandId": f"command_{thread}", "resultId": completed["resultId"], "jobIds": ids[:2]}


def _counts(factory):
    with factory() as session:
        return tuple(session.scalar(select(func.count()).select_from(model)) for model in (
            ApplicationWorkspaceORM, ResumeVariantORM, ExecutionActionItemORM, ApplicationTimelineEventORM, AnalysisExecutionReceiptORM))


def test_one_click_materializes_saved_facts_and_exact_replays_without_regeneration(synthetic_api, monkeypatch):
    client, factory, ids = synthetic_api
    body = _completed(client, ids)
    monkeypatch.setattr(BuildJobPreparationBundleUseCase, "execute", lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not recompute latest")))
    response = client.post("/api/v1/career-agent/runs/execution/execution", json=body)
    assert response.status_code == 200, response.text
    result = response.json()
    assert len(result["items"]) == 2
    assert all(item["resumeVariantId"] and len(item["actionIds"]) == 2 for item in result["items"])
    assert _counts(factory) == (2, 2, 4, 4, 1)
    assert client.post("/api/v1/career-agent/runs/execution/execution", json=body).json() == result
    assert client.get("/api/v1/career-agent/runs/execution/execution").json()["execution"] == result
    assert _counts(factory) == (2, 2, 4, 4, 1)
    workspace = result["items"][0]["workspaceId"]
    root = f"/api/v1/application-workspaces/{workspace}"
    # The old Job detail entry must open the same local-user workspace, not a parallel one.
    entry = client.post("/api/v1/application-workspaces", json={"jobId": result["items"][0]["jobId"],
        "actorId": "local-user", "idempotencyKey": f"web-application-workspace:{result['items'][0]['jobId']}"})
    assert entry.status_code == 201 and entry.json()["workspaceId"] == workspace
    original = client.get(f"{root}/preparation").json()
    assert original["isCurrent"] and original["resultId"] == body["resultId"]
    assert original["preparation"]["resumeDelta"]["highlights"]
    assert client.get(f"{root}/resume-variant/proposal").status_code == 200
    assert client.get(f"{root}/interview/questions").status_code == 200
    assert _counts(factory) == (2, 2, 4, 4, 1)  # No write-on-read.
    with factory.begin() as session:
        session.add(UserProfileORM(id="after_start_profile", profile_key="default", version=2,
            headline="Synthetic confirmed facts changed after start", years_of_experience=6))
    historical = client.get(f"{root}/preparation").json()
    assert not historical["isCurrent"]
    assert historical["preparation"] == original["preparation"]
    assert client.get(f"{root}/resume-variant/proposal").status_code == 200
    assert client.get(f"{root}/interview/questions").status_code == 200
    # The same command is a receipt replay even after facts change, not new materials.
    assert client.post("/api/v1/career-agent/runs/execution/execution", json=body).json() == result
    different = client.post("/api/v1/career-agent/runs/execution/execution", json={**body, "commandId": "new_after_changed_facts"})
    assert different.status_code == 409 and different.json()["error"]["code"] == "analysis_execution_facts_stale"
    # Facts becoming stale must not stop recording a real action status.
    action_id = result["items"][0]["actionIds"][0]
    for expected, new in (("todo", "in_progress"), ("in_progress", "done")):
        updated = client.post(f"{root}/actions/{action_id}/status", json={
            "actorId": "local-user", "expectedStatus": expected, "newStatus": new})
        assert updated.status_code == 200, updated.text
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(UserProfileORM)) == 2
        assert session.get(ExecutionActionItemORM, action_id).status == "done"


def test_save_failure_rolls_back_all_targets_and_original_command_can_retry(synthetic_api):
    client, factory, ids = synthetic_api
    body = _completed(client, ids, "rollback_execution")
    with factory.begin() as session:
        session.execute(text("""CREATE TRIGGER abort_execution_receipt BEFORE INSERT ON analysis_execution_receipts
            BEGIN SELECT RAISE(ABORT, 'injected after all preparation writes'); END"""))
    path = "/api/v1/career-agent/runs/rollback_execution/execution"
    response = client.post(path, json=body)
    assert response.status_code == 503, response.text
    assert response.json()["error"]["retryable"]
    assert _counts(factory) == (0, 0, 0, 0, 0)
    assert client.get(path).json() == {"execution": None}
    with factory.begin() as session:
        session.execute(text("DROP TRIGGER abort_execution_receipt"))
    assert client.post(path, json=body).status_code == 200
    assert _counts(factory) == (2, 2, 4, 4, 1)


def test_same_command_changed_content_conflicts_and_unconfirmed_scope_rejected(synthetic_api):
    client, factory, ids = synthetic_api
    body = _completed(client, ids, "content")
    path = "/api/v1/career-agent/runs/content/execution"
    assert client.post(path, json=body).status_code == 200
    for change in ({"jobIds": ids[:1]}, {"resultId": "different"}):
        response = client.post(path, json={**body, **change})
        assert response.status_code == 409 and response.json()["error"]["code"] == "analysis_execution_command_conflict"
    response = client.post(path, json={**body, "commandId": "outside", "jobIds": [ids[2]]})
    assert response.status_code == 409 and response.json()["error"]["code"] == "analysis_execution_selection_invalid"
    assert _counts(factory) == (2, 2, 4, 4, 1)


def test_concurrent_commands_reuse_workspace_materials_and_do_not_reset_completed_actions(synthetic_api):
    client, factory, ids = synthetic_api
    body = _completed(client, ids, "concurrent")
    path = "/api/v1/career-agent/runs/concurrent/execution"
    barrier = Barrier(2)
    def send(command_id):
        barrier.wait(timeout=5)
        return client.post(path, json={**body, "commandId": command_id})
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(send, ("same", "same")))
    assert [item.status_code for item in responses] == [200, 200], [item.text for item in responses]
    assert responses[0].json() == responses[1].json()
    assert _counts(factory) == (2, 2, 4, 4, 1)
    result = responses[0].json()
    first = result["items"][0]
    with factory.begin() as session:
        session.get(ExecutionActionItemORM, first["actionIds"][0]).status = "done"
        session.get(ApplicationWorkspaceORM, first["workspaceId"]).status = "applied"
    barrier = Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(send, ("different_one", "different_two")))
    assert [item.status_code for item in responses] == [200, 200]
    assert _counts(factory) == (2, 2, 4, 4, 3)
    assert all(item.json()["items"] == result["items"] for item in responses)
    with factory() as session:
        assert session.get(ExecutionActionItemORM, first["actionIds"][0]).status == "done"
        assert session.get(ApplicationWorkspaceORM, first["workspaceId"]).status == "applied"


def test_new_analysis_reuses_compatible_materials_and_preserves_original_source_and_manual_state(synthetic_api):
    client, factory, ids = synthetic_api
    body = _completed(client, ids, "first_analysis")
    original = client.post("/api/v1/career-agent/runs/first_analysis/execution", json=body).json()
    workspace = original["items"][0]["workspaceId"]
    with factory.begin() as session:
        session.get(ApplicationWorkspaceORM, workspace).status = "interviewing"
    body2 = _completed(client, ids, "second_analysis")
    response = client.post("/api/v1/career-agent/runs/second_analysis/execution", json=body2)
    assert response.status_code == 200, response.text
    assert response.json()["items"] == original["items"]
    assert _counts(factory) == (2, 2, 4, 4, 2)
    with factory() as session:
        row = session.get(ApplicationWorkspaceORM, workspace)
        assert row.status == "interviewing"
        assert row.profile_version == 1
        assert row.current_analysis_result_id == body2["resultId"]
        assert session.get(ExecutionActionItemORM, original["items"][0]["actionIds"][0]).source_analysis_result_id == body["resultId"]


def test_shared_execution_schemas_match_the_actual_python_consumers():
    import json
    from pathlib import Path
    from app.api.v1.schemas.analysis_execution import (
        StartAnalysisExecutionRequest, AnalysisExecutionResponse, AnalysisExecutionStatusResponse, WorkspaceSavedPreparationResponse,
    )
    from app.api.v1.schemas.application_workspace import ApplicationWorkspaceResponse, ExecutionActionResponse
    root = Path(__file__).parents[3] / "packages/contracts/schemas"
    for model, name in ((StartAnalysisExecutionRequest, "analysis-execution-request"),
        (AnalysisExecutionResponse, "analysis-execution-result"), (AnalysisExecutionStatusResponse, "analysis-execution-status"),
        (WorkspaceSavedPreparationResponse, "workspace-saved-preparation"), (ApplicationWorkspaceResponse, "application-workspace"),
        (ExecutionActionResponse, "application-execution-action")):
        schema = json.loads((root / f"{name}.schema.json").read_text())
        schema.pop("$id"); schema.pop("$schema")
        assert schema == model.model_json_schema(by_alias=True)


def test_partial_commands_merge_in_original_confirmed_order_not_sorted_job_ids(synthetic_api):
    client, _, ids = synthetic_api
    state = start(client, ids, 'reverse_targets')
    selected = list(reversed(ids[:2]))
    completed = client.post('/api/v1/career-agent/runs/reverse_targets/resume', json={
        'interruptId': state['interruptId'], 'actionId': 'reverse_confirm',
        'decision': 'edit', 'selectedJobIds': selected})
    assert completed.status_code == 200, completed.text
    path = '/api/v1/career-agent/runs/reverse_targets/execution'
    result_id = completed.json()['resultId']
    for n, job_id in enumerate(selected):
        response = client.post(path, json={'commandId': f'partial_{n}', 'resultId': result_id, 'jobIds': [job_id]})
        assert response.status_code == 200, response.text
    queried = client.get(path).json()['execution']
    assert [item['jobId'] for item in queried['items']] == selected

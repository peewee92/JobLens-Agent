"""Real SQLite + existing workflow + HTTP MockTransport. Never a paid call."""
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import httpx
import pytest
from sqlalchemy import text
from app.api import deps
from app.main import app
from app.core.config import Settings
from app.application.job_requirements.authorized import AuthorizedRequirementExtraction
from app.repositories.sqlalchemy_requirement_call import SqlAlchemyRequirementCalls, AuthorizedRequirementUnitOfWork
from app.llm.authorized_requirement_factory import authorized_extractor_factory
from .test_career_agent_analysis_snapshot import synthetic_api

DESCRIPTION = "岗位职责与要求：\n熟练掌握 Python 和 FastAPI，并具备后端系统设计经验，能够独立完成服务开发与维护。"


def response(request):
    body = json.loads(request.content)
    assert body["max_output_tokens"] == 4096
    assert request.extensions["timeout"]["read"] == 60
    output = {"requirements": [{"type": "skill", "originalText": "熟练掌握 Python 和 FastAPI",
        "normalizedCapability": "Python", "importance": "must_have", "sourceCandidateId": "S0002", "confidence": .95}]}
    return httpx.Response(200, json={"output": [{"type": "message", "content": [
        {"type": "output_text", "text": json.dumps(output)}]}], "usage": {"input_tokens": 100, "output_tokens": 40}})


@pytest.fixture
def authorized(synthetic_api):
    client, factory, ids = synthetic_api
    with factory.begin() as session:
        session.execute(text("UPDATE jobs SET description=:d WHERE id=:id"), {"d": DESCRIPTION, "id": ids[0]})
    calls = []
    def handler(request):
        calls.append(request)
        return response(request)
    settings = Settings(_env_file=None,
        requirement_extractor_provider="openai", requirement_extractor_model="test-only",
        openai_api_key="never-live", openai_base_url="https://example.test/v1")
    journal = SqlAlchemyRequirementCalls(factory)
    service = AuthorizedRequirementExtraction(settings=settings,
        jobs=deps.get_job_query_repository(), requirements=deps.get_job_requirement_query_repository(),
        journal=journal, uow_factory=lambda action: AuthorizedRequirementUnitOfWork(factory, action), traces=deps.get_trace_uow_factory(),
        extractor_factory=authorized_extractor_factory(settings, journal, lambda: httpx.MockTransport(handler)))
    app.dependency_overrides[deps.get_authorized_requirement_extraction] = lambda: service
    yield client, factory, ids[0], service, calls
    app.dependency_overrides.pop(deps.get_authorized_requirement_extraction, None)


def command(client, job, action="authorized-one"):
    plan = client.get(f"/api/v1/jobs/{job}/requirement-call-plan").json()
    return dict(actionId=action, planDigest=plan["planDigest"], confirmed=True, maxProviderCalls=1)


def test_authorized_success_replay_and_saved_result(authorized):
    client, factory, job, service, calls = authorized
    path = f"/api/v1/jobs/{job}"
    payload = command(client, job)
    result = client.post(path + "/requirement-calls", json=payload)
    assert result.status_code == 200, result.text
    saved = result.json()
    assert saved["status"] == "completed", saved
    assert saved["attempts"] == 1 and saved["inputTokens"] == 100 and saved["outputTokens"] == 40
    assert client.get(path + "/requirements").json()["extractionId"] == saved["extractionId"]
    assert client.post(path + "/requirement-calls", json=payload).json() == saved
    assert client.get(path + "/requirement-calls/authorized-one").json() == saved
    assert len(calls) == 1
    assert "never-live" not in json.dumps(saved)
    changed = {**payload, "confirmed": False}
    assert client.post(path + "/requirement-calls", json=changed).status_code == 409
    assert len(calls) == 1


@pytest.mark.parametrize("change", ["no_consent", "zero_budget", "missing_budget", "stale", "inactive"])
def test_no_authorization_or_stale_means_zero_http(authorized, change):
    client, factory, job, service, calls = authorized
    payload = command(client, job)
    if change == "no_consent": payload["confirmed"] = False
    if change == "zero_budget": payload["maxProviderCalls"] = 0
    if change == "missing_budget": payload.pop("maxProviderCalls")
    if change == "stale":
        with factory.begin() as session:
            session.execute(text("UPDATE jobs SET description='changed' WHERE id=:id"), {"id": job})
    if change == "inactive":
        with factory.begin() as session:
            session.execute(text("UPDATE jobs SET user_marked_inactive=1 WHERE id=:id"), {"id": job})
    assert client.post(f"/api/v1/jobs/{job}/requirement-calls", json=payload).status_code == 409
    assert not calls


def test_timeout_unknown_is_never_automatically_retried(authorized):
    client, factory, job, service, calls = authorized
    def timeout(request):
        calls.append(request)
        raise httpx.ReadTimeout("test-only", request=request)
    service.extractor_factory = authorized_extractor_factory(service.settings, service.journal, lambda: httpx.MockTransport(timeout))
    path = f"/api/v1/jobs/{job}/requirement-calls"
    payload = command(client, job)
    saved = client.post(path, json=payload).json()
    assert saved["status"] == "uncertain" and saved["attempts"] == 1
    assert client.post(path, json=payload).json() == saved
    assert client.post(path, json=command(client, job, "second")).status_code == 409
    assert len(calls) == 1
    acknowledged = {**command(client, job, "second"), "acknowledgedPriorRequestId": payload["actionId"]}
    assert client.post(path, json=acknowledged).json()["status"] == "uncertain"
    assert len(calls) == 2


def test_artifact_and_completion_failure_roll_back_together(authorized):
    client, factory, job, service, calls = authorized
    with factory.begin() as session:
        count = session.execute(text("SELECT count(*) FROM job_requirement_extractions")).scalar_one()
        session.execute(text("CREATE TRIGGER stop_call_commit BEFORE UPDATE OF status ON requirement_calls WHEN NEW.status='completed' BEGIN SELECT RAISE(ABORT, 'test'); END"))
    payload = command(client, job)
    saved = client.post(f"/api/v1/jobs/{job}/requirement-calls", json=payload).json()
    assert saved["status"] == "failed", saved
    assert saved["attempts"] == 1 and saved["inputTokens"] == 100
    with factory() as session:
        assert session.execute(text("SELECT count(*) FROM job_requirement_extractions")).scalar_one() == count
    assert client.post(f"/api/v1/jobs/{job}/requirement-calls", json=payload).json() == saved
    assert len(calls) == 1


def test_two_tabs_share_one_attempt_and_reject_competing_command(authorized):
    client, factory, job, service, calls = authorized
    entered, release = Event(), Event()
    def wait(request):
        calls.append(request)
        entered.set()
        assert release.wait(10)
        return response(request)
    service.extractor_factory = authorized_extractor_factory(service.settings, service.journal, lambda: httpx.MockTransport(wait))
    payload = command(client, job)
    path = f"/api/v1/jobs/{job}/requirement-calls"
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(client.post, path, json=payload)
        try:
            assert entered.wait(10)
            assert client.post(path, json=payload).json()["status"] == "running"
            assert client.post(path, json={**payload, "actionId": "different"}).status_code == 409
        finally:
            release.set()
        assert first.result().json()["status"] == "completed"
    assert len(calls) == 1


def test_facts_change_during_http_preserves_old_extraction(authorized):
    client, factory, job, service, calls = authorized
    old = client.get(f"/api/v1/jobs/{job}/requirements").json()["extractionId"]
    def changed(request):
        calls.append(request)
        with factory.begin() as session:
            session.execute(text("UPDATE jobs SET description='Changed during call' WHERE id=:id"), {"id": job})
        return response(request)
    service.extractor_factory = authorized_extractor_factory(service.settings, service.journal, lambda: httpx.MockTransport(changed))
    saved = client.post(f"/api/v1/jobs/{job}/requirement-calls", json=command(client, job)).json()
    assert saved["status"] == "failed" and saved["attempts"] == 1
    assert client.get(f"/api/v1/jobs/{job}/requirements").json()["extractionId"] == old


def test_transport_checks_facts_again_before_sending(authorized):
    client, factory, job, service, calls = authorized
    original = service.extractor_factory
    from contextlib import contextmanager
    @contextmanager
    def changed(action_id, snapshot):
        with factory.begin() as session:
            session.execute(text("UPDATE jobs SET description='Changed before send with a sufficiently long description for the existing extraction workflow' WHERE id=:id"), {"id": job})
        with original(action_id, snapshot) as adapter:
            yield adapter
    service.extractor_factory = changed
    saved = client.post(f"/api/v1/jobs/{job}/requirement-calls", json=command(client, job)).json()
    assert saved["status"] == "failed" and saved["attempts"] == 0
    assert not calls
    with factory() as session:
        trace = session.execute(text("SELECT input_refs FROM trace_spans WHERE model='test-only' ORDER BY created_at DESC LIMIT 1")).scalar_one()
        assert json.loads(trace)["providerCalls"] == 0


@pytest.mark.parametrize("status", [402, 429, 500, 503, 307])
def test_http_failures_do_not_retry_or_follow_redirects(authorized, status):
    client, factory, job, service, calls = authorized
    def failed(request):
        calls.append(request)
        return httpx.Response(status, headers={"location": "https://not-allowed.test"}, json={"error": "test"})
    service.extractor_factory = authorized_extractor_factory(service.settings, service.journal, lambda: httpx.MockTransport(failed))
    saved = client.post(f"/api/v1/jobs/{job}/requirement-calls", json=command(client, job)).json()
    assert saved["status"] == "failed" and saved["attempts"] == 1
    assert saved["inputTokens"] is None and saved["outputTokens"] is None
    assert len(calls) == 1
    if status == 402:
        assert saved["responseStatus"] == 402
        assert saved["errorCode"] == "provider_payment_required"
        # An identical retry returns the saved failure, not another paid attempt.
        assert client.post(f"/api/v1/jobs/{job}/requirement-calls", json=command(client, job)).json() == saved
        assert len(calls) == 1


def test_expired_process_needs_new_explicit_acknowledgment_and_fences_old_worker(authorized):
    client, factory, job, service, calls = authorized
    entered, release = Event(), Event()
    def delayed(request):
        calls.append(request)
        if len(calls) == 1:
            entered.set()
            assert release.wait(10)
        return response(request)
    service.extractor_factory = authorized_extractor_factory(service.settings, service.journal, lambda: httpx.MockTransport(delayed))
    payload = command(client, job)
    path = f"/api/v1/jobs/{job}/requirement-calls"
    with ThreadPoolExecutor(max_workers=2) as pool:
        old = pool.submit(client.post, path, json=payload)
        try:
            assert entered.wait(10)
            with factory.begin() as session:
                session.execute(text("UPDATE requirement_calls SET created_at=datetime('now','-5 minutes') WHERE action_id=:id"), {"id": payload["actionId"]})
            assert client.get(path + "/" + payload["actionId"]).json()["status"] == "uncertain"
            assert client.post(path, json=payload).json()["status"] == "uncertain"
            next_command = {**command(client, job, "new-worker"), "acknowledgedPriorRequestId": payload["actionId"]}
            new = client.post(path, json=next_command).json()
            assert new["status"] == "completed", new
        finally:
            release.set()
        assert old.result().json()["status"] == "uncertain"
    assert client.get(f"/api/v1/jobs/{job}/requirements").json()["extractionId"] == new["extractionId"]
    assert len(calls) == 2


def test_shared_call_contracts_match_python():
    from pathlib import Path
    from app.api.v1.schemas.requirement_calls import RequirementCallCommand, RequirementCallPlan, RequirementCallRecord
    root = Path(__file__).resolve().parents[3] / "packages/contracts/schemas"
    for name, model in (("requirement-call-command", RequirementCallCommand), ("requirement-call-plan", RequirementCallPlan), ("requirement-call-record", RequirementCallRecord)):
        schema = json.loads((root / f"{name}.schema.json").read_text())
        schema.pop("$schema")
        assert schema == model.model_json_schema(by_alias=True)

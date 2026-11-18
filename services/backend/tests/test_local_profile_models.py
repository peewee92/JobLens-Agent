from dataclasses import replace
from unittest.mock import Mock
import httpx
import pytest
from fastapi.testclient import TestClient
from app.core.config import Settings
from app.api.v1 import local_profile_models as api
from app.byok import api as shared
from app.byok.context import ModelSession
from app.demo.sessions import DemoError
from app.main import app

TEXT = "Python 应用工程师，有两年工作经验。负责 Python 和 FastAPI 服务开发，使用 SQL 建立检索和回归测试，参与工具调用项目。"


@pytest.fixture
def client(monkeypatch):
    configured = Settings(_env_file=None, app_env="local", profile_extractor_provider="openai",
        profile_extractor_model="test-model", openai_api_key="test-not-a-real-secret",
        openai_base_url="https://models.example.com/v1", profile_extractor_api_style="chat_completions")
    monkeypatch.setenv("JOBLENS_LOCAL_PRODUCT", "1")
    monkeypatch.setattr(api, "get_settings", lambda: configured)
    from contextlib import contextmanager
    from app.api import deps
    @contextmanager
    def trace():
        yield Mock()
    monkeypatch.setattr(deps, "get_trace_uow_factory", lambda: trace)
    api.model_session.cache_clear()
    with TestClient(app) as value:
        yield value
    api.model_session.cache_clear()


def test_local_plan_never_sends_calls_and_does_not_leak_credentials(client, monkeypatch):
    send = Mock(side_effect=AssertionError("no network while reading plans"))
    monkeypatch.setattr(shared.RecordedTransport, "handle_request", send)
    assert client.get("/api/v1/local/profile-model/status").json() == {"available": True}
    result = client.post("/api/v1/local/profile-model/plan", json={"resumeText": TEXT})
    assert result.status_code == 200
    data = result.json()
    assert data["destination"] == "models.example.com"
    assert data["model"] == "test-model"
    assert data["maxProviderCalls"] == 1
    assert data["maxOutputTokens"] == 4096
    assert "test-not-a-real-secret" not in result.text
    assert TEXT not in result.text
    assert not send.called


def test_local_model_endpoint_disabled_outside_personal_launcher(client, monkeypatch):
    monkeypatch.delenv("JOBLENS_LOCAL_PRODUCT")
    assert client.get("/api/v1/local/profile-model/status").status_code == 404
    assert client.post("/api/v1/local/profile-model/plan", json={"resumeText": TEXT}).status_code == 404


def test_missing_model_stops_before_plan_or_dispatch(client, monkeypatch):
    monkeypatch.setattr(api, "configuration", lambda: None)
    assert client.get("/api/v1/local/profile-model/status").json() == {"available": False}
    assert client.post("/api/v1/local/profile-model/plan", json={"resumeText": TEXT}).status_code == 409


def test_invalid_file_fails_locally_without_plan(client):
    response = client.post("/api/v1/local/profile-model/file-plan",
        files={"file": ("not-a-resume.pdf", b"not a pdf", "application/pdf")})
    assert response.status_code == 415
    assert not api.model_session().plans
    assert not api.model_session().calls


def test_missing_authorization_changed_digest_and_replay_do_not_resend(client, monkeypatch):
    def rejected_provider(self, request):
        return httpx.Response(401, json={"error": "no valid credentials"}, request=request)
    send = Mock(side_effect=rejected_provider, autospec=False)
    monkeypatch.setattr(shared.RecordedTransport, "handle_request", lambda self, request: send(self, request))
    plan = client.post("/api/v1/local/profile-model/plan", json={"resumeText": TEXT}).json()
    body = {"actionId": "single-call", "planDigest": plan["planDigest"], "confirmed": False, "maxProviderCalls": 1}
    assert client.post("/api/v1/local/profile-model/calls", json=body).status_code == 409
    body.update(confirmed=True, planDigest="0" * 64)
    assert client.post("/api/v1/local/profile-model/calls", json=body).status_code == 409
    assert send.call_count == 0
    body["planDigest"] = plan["planDigest"]
    first = client.post("/api/v1/local/profile-model/calls", json=body)
    assert first.status_code == 200
    assert first.json()["status"] == "failed"
    second = client.post("/api/v1/local/profile-model/calls", json=body)
    assert second.json() == first.json()
    assert send.call_count == 1


def test_profile_parser_returns_text_plan_without_model(client, monkeypatch):
    from app.api.deps import get_resume_document_parser
    from app.application.resume_documents import ParsedResumeDocument
    parser = Mock()
    parser.parse.return_value = ParsedResumeDocument("resume.pdf", "pdf", TEXT, 1)
    app.dependency_overrides[get_resume_document_parser] = lambda: parser
    try:
        response = client.post("/api/v1/local/profile-model/file-plan",
            files={"file": ("resume.pdf", b"%PDF-1.7 fake for parser override", "application/pdf")})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json()["inputCharacters"] == len(TEXT)
    assert not api.model_session().calls

import json
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker
import pytest

from app.api.v1.url_capture import CAPTURE_PATH, get_url_capture
from app.application.job_imports.manual import ManualJobInput
from app.application.url_capture.models import UrlJobCaptureRequest
from app.application.url_capture.ssrf_guard import GuardedHttpClient, PageResponse
from app.application.url_capture.use_case import CaptureJobUrlUseCase
from app.cloud.private_app import create_private_app
from app.demo.public_app import create_public_app
from app.main import create_app

CONTRACTS = Path(__file__).resolve().parents[3] / "packages" / "contracts"


def validator(kind):
    schema = json.loads((CONTRACTS / "schemas" / f"url-job-capture-{kind}.schema.json").read_text())
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


@pytest.fixture
def local(monkeypatch):
    monkeypatch.setenv("JOBLENS_URL_CAPTURE", "1")
    monkeypatch.setattr("app.api.v1.url_capture.get_settings", lambda: SimpleNamespace(app_env="local"))
    monkeypatch.delenv("JOBLENS_DEMO", raising=False)
    monkeypatch.delenv("JOBLENS_PUBLIC_DEMO", raising=False)

    async def get(url, _address, _budget):
        if url.path == "/restricted":
            return PageResponse(str(url), 403, {}, b"")
        if url.path == "/unavailable":
            return PageResponse(str(url), 404, {}, b"")
        body = b'<main><h1>Engineer</h1><div class="company-name">Example</div><div class="job-description">Build tools.</div></main>'
        return PageResponse(str(url), 200, {"content-type": "text/html"}, body)

    async def resolve(*_):
        return ["93.184.216.34"]

    class NoBrowser:
        async def render(self, *_):
            pytest.fail("browser should not start for local contract fixtures")

    class NoDatabase:
        def __getattr__(self, *_):
            pytest.fail("capture must not access the database")

    from app.db.context import current_database
    marker = current_database.set(NoDatabase())
    try:
        app = create_app()
        app.dependency_overrides[get_url_capture] = lambda: CaptureJobUrlUseCase(GuardedHttpClient(resolve, get), NoBrowser())
        with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 55001)) as client:
            yield client
    finally:
        current_database.reset(marker)


def test_example_schema_and_diagnostics():
    example = json.loads((CONTRACTS / "examples" / "url-job-capture-response.example.json").read_text())
    validator("response").validate(example)
    assert example["diagnostics"]["descriptionLength"] == len(example["draft"]["description"])
    assert example["diagnostics"]["rawTextLength"] >= len(example["draft"]["description"])
    ManualJobInput.model_validate(example["draft"])


@pytest.mark.parametrize(("suffix", "status"), [("/", "captured"), ("/restricted", "needs_human_intervention"), ("/unavailable", "failed")])
def test_local_capture_response_validates_and_does_not_use_database(local, suffix, status):
    payload = {"url": f"https://jobs.test{suffix}", "timeoutMs": 3000}
    validator("request").validate(UrlJobCaptureRequest.model_validate(payload).model_dump(mode="json"))
    response = local.post(CAPTURE_PATH, json=payload)
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    body = response.json()
    validator("response").validate(body)
    assert body["status"] == status and body["providerCalls"] == 0
    if status == "captured":
        ManualJobInput.model_validate(body["draft"])
    else:
        assert body["draft"] is None


@pytest.mark.parametrize("payload", [
    {"url": "https://?oops"}, {"url": "file:///not-a-job-posting"}, {"url": "https://jobs.test/a b"},
    {"url": "https://jobs.test/", "timeoutMs": 2999}, {"url": "https://jobs.test/", "timeoutMs": 25001},
    {"url": "https://jobs.test/", "timeoutMs": "3000"}, {"url": "https://jobs.test/", "renderMode": "other"},
    {"url": "https://jobs.test/", "extra": "rejected"},
])
def test_invalid_requests_return_422(local, payload):
    assert local.post(CAPTURE_PATH, json=payload).status_code == 422


def test_loopback_target_ssrf_and_cross_origin_requests_are_rejected(local):
    denied = local.post(CAPTURE_PATH, json={"url": "http://127.0.0.1/"})
    assert denied.status_code == 403 and denied.json()["error"]["code"] == "url_capture_ssrf_blocked"
    for headers in [{"origin": "https://external.test"}, {"host": "wrong.test"}]:
        denied = local.post(CAPTURE_PATH, json={"url": "https://jobs.test/"}, headers=headers)
        assert denied.status_code == 403 and denied.json()["error"]["code"] == "url_capture_forbidden"


def test_enabled_flag_is_required(local, monkeypatch):
    monkeypatch.delenv("JOBLENS_URL_CAPTURE")
    monkeypatch.delenv("JOBLENS_LOCAL_PRODUCT", raising=False)
    assert local.post(CAPTURE_PATH, json={"url": "https://jobs.test/"}).status_code == 403


def test_public_denies_before_authentication_or_body_and_private_never_mounts(monkeypatch):
    monkeypatch.setenv("JOBLENS_URL_CAPTURE", "1")
    for byok in (True, False):
        public = create_public_app(None, secret="test-secret" * 4, origin="https://demo.test", byok_enabled=byok)
        with TestClient(public) as client:
            response = client.post(CAPTURE_PATH, content=b"not JSON")
        assert response.status_code == 403 and response.json()["error"]["code"] == "url_capture_forbidden"

    from app.cloud.boundary import identity_signature
    import time
    secret = b"test-only-private-workspace-secret-not-deployed"
    owner, issued = "owner", str(int(time.time()))
    private = create_private_app({owner: object()}, secret)
    with TestClient(private) as client:
        assert CAPTURE_PATH not in {getattr(route, "path", None) for route in private.routes}
        response = client.post(CAPTURE_PATH, json={"url": "https://jobs.test/"}, headers={
            "x-joblens-owner": owner, "x-joblens-issued": issued,
            "x-joblens-workspace-signature": identity_signature(secret, owner, issued, "POST", CAPTURE_PATH),
        })
        assert response.status_code in {404, 405}

"""Legacy HTTP dependency must not construct a live semantic provider."""
import pytest

from app.api import deps
from app.application.semantic_match.errors import SemanticMatcherUnavailableError
from app.core.config import Settings
from app.llm.semantic_matchers import FixtureSemanticMatcher


def test_http_live_configuration_does_not_build_or_call_provider(monkeypatch):
    monkeypatch.setattr(deps, "get_settings", lambda: Settings(
        _env_file=None, semantic_match_provider=" OpenAI ", semantic_match_model="test",
        openai_api_key="not-a-real-key"))
    calls = []
    monkeypatch.setattr(deps, "build_semantic_matcher", lambda settings: calls.append(settings))
    matcher = deps.get_semantic_matcher()
    with pytest.raises(SemanticMatcherUnavailableError, match="per-request model authorization"):
        matcher.match(())
    assert calls == []


def test_http_fixture_remains_available(monkeypatch):
    monkeypatch.setattr(deps, "get_settings", lambda: Settings(_env_file=None, semantic_match_provider="fixture"))
    assert isinstance(deps.get_semantic_matcher(), FixtureSemanticMatcher)


def test_http_error_reports_missing_authorization():
    from fastapi.testclient import TestClient
    from app.application.semantic_match.errors import SemanticModelAuthorizationRequiredError
    from app.main import app

    class BlockedRun:
        def execute(self, job_id):
            raise SemanticModelAuthorizationRequiredError("authorization required")

    app.dependency_overrides[deps.get_semantic_match_use_case] = BlockedRun
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/jobs/example/semantic-match")
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "semantic_model_authorization_required"
    finally:
        app.dependency_overrides.pop(deps.get_semantic_match_use_case, None)


@pytest.mark.parametrize("provider, fallback", [("openai", "disabled"), ("fixture", "openai"), ("openai", "openai")])
def test_http_requirement_rejects_live_primary_or_fallback_without_factory(monkeypatch, provider, fallback):
    from app.application.job_requirements.errors import RequirementModelAuthorizationRequiredError
    monkeypatch.setattr(deps, "get_settings", lambda: Settings(_env_file=None,
        requirement_extractor_provider=provider, requirement_extractor_fallback_provider=fallback))
    calls = []
    monkeypatch.setattr(deps, "build_job_requirement_extractor", lambda settings: calls.append(settings))
    extractor = deps.get_job_requirement_extractor()
    with pytest.raises(RequirementModelAuthorizationRequiredError):
        extractor.extract("job description")
    assert calls == []


def test_http_profile_rejects_live_without_factory(monkeypatch):
    from app.application.profile_extraction.errors import ProfileModelAuthorizationRequiredError
    monkeypatch.setattr(deps, "get_settings", lambda: Settings(_env_file=None, profile_extractor_provider="openai"))
    calls = []
    monkeypatch.setattr(deps, "build_profile_extractor", lambda settings: calls.append(settings))
    with pytest.raises(ProfileModelAuthorizationRequiredError):
        deps.get_profile_extractor().extract("resume")
    assert calls == []


def test_http_extraction_fixtures_remain_available(monkeypatch):
    from app.llm.profile_extractors import FixtureProfileExtractor
    from app.llm.job_requirement_extractors import FixtureJobRequirementExtractor
    monkeypatch.setattr(deps, "get_settings", lambda: Settings(_env_file=None,
        profile_extractor_provider="fixture", requirement_extractor_provider="fixture"))
    assert isinstance(deps.get_profile_extractor(), FixtureProfileExtractor)
    assert isinstance(deps.get_job_requirement_extractor(), FixtureJobRequirementExtractor)

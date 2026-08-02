import pytest

from app.application.job_imports.canonical_key import (
    build_canonical_key,
    extract_source_job_id,
    normalize_source_url,
)
from app.application.job_imports.errors import CanonicalIdentityError


def test_normalize_boss_url_removes_tracking_and_canonicalizes_host() -> None:
    normalized = normalize_source_url(
        "http://m.zhipin.com//job_detail/AbC-_.html?ka=search#top",
        source="boss",
    )

    assert normalized == "https://www.zhipin.com/job_detail/AbC-_.html"
    assert extract_source_job_id(normalized, source="boss") == "AbC-_"


def test_canonical_key_prefers_external_source_id() -> None:
    key = build_canonical_key(
        source="BOSS",
        source_job_id="  AbC:123  ",
        normalized_source_url="https://www.zhipin.com/job_detail/other.html",
        company="Example",
        title="Engineer",
        area="Wuhan",
    )

    assert key == "v1:boss:id:AbC%3A123"


def test_canonical_key_uses_url_hash_when_external_id_is_missing() -> None:
    first = build_canonical_key(
        source="boss",
        source_job_id=None,
        normalized_source_url="https://www.zhipin.com/jobs/123",
        company="Example",
        title="Engineer",
        area="Wuhan",
    )
    second = build_canonical_key(
        source="boss",
        source_job_id=None,
        normalized_source_url="https://www.zhipin.com/jobs/123",
        company="Changed company",
        title="Changed title",
        area=None,
    )

    assert first == second
    assert first.startswith("v1:boss:url:")


def test_fingerprint_fallback_is_stable_for_case_and_whitespace() -> None:
    first = build_canonical_key(
        source="boss",
        source_job_id=None,
        normalized_source_url=None,
        company="  示例 公司 ",
        title="AI   Engineer",
        area="武汉",
    )
    second = build_canonical_key(
        source="BOSS",
        source_job_id=None,
        normalized_source_url=None,
        company="示例 公司",
        title="ai engineer",
        area="武汉",
    )

    assert first == second
    assert first.startswith("v1:boss:fingerprint:")


def test_fingerprint_fallback_requires_company_and_title() -> None:
    with pytest.raises(CanonicalIdentityError):
        build_canonical_key(
            source="boss",
            source_job_id=None,
            normalized_source_url=None,
            company=None,
            title="Engineer",
            area="Wuhan",
        )


def test_boss_url_rejects_untrusted_host() -> None:
    with pytest.raises(CanonicalIdentityError, match="zhipin.com"):
        normalize_source_url(
            "https://example.com/job_detail/abc.html", source="boss"
        )

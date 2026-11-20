import asyncio
import json
import time

import pytest

from app.application.url_capture.html_extractor import grade_description
from app.application.url_capture.models import UrlJobCaptureRequest
from app.application.url_capture.playwright_fetcher import PlaywrightFetcher, RenderedPage
from app.application.url_capture.ssrf_guard import CaptureError, PageResponse
from app.application.url_capture.use_case import CaptureJobUrlUseCase


URL = "https://jobs.example.test/a"
JD = "Responsibilities: " + ("Maintain accessible tools. Write tests for reliable features. " * 5)
SHELL = '<main id="app"></main><script src="/jobs.js"></script>'
STATIC = f'<main><h1>Software Engineer</h1><div data-company-name="Example"></div><section class="job-description">{JD}</section></main>'


class Http:
    def __init__(self, html, status=200, *, url=URL):
        self.data = PageResponse(url, status, {"content-type": "text/html; charset=utf-8"}, html.encode())

    async def fetch(self, _url, _budget):
        return self.data


class Browser:
    def __init__(self, result):
        self.result = result
        self.called = 0

    async def render(self, *_args):
        self.called += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def capture(http, browser, **kwargs):
    return asyncio.run(CaptureJobUrlUseCase(http, browser).execute(UrlJobCaptureRequest(url=URL, **kwargs)))


def test_structured_data_wins_without_chromium_or_career_context():
    data = {"@graph": [{"@type": ["Thing", "JobPosting"], "title": "Data Engineer",
                        "hiringOrganization": {"name": "Example"}, "description": f"<h3>Responsibilities</h3><p>{JD}</p>"}]}
    html = f'<script type="application/ld+json">{json.dumps(data)}</script>{STATIC}'
    browser = Browser(AssertionError("structured fast path must not start browser"))
    r = capture(Http(html), browser)
    assert (r.status, r.qualityGrade, r.extractionMethod) == ("captured", "full_jd", "json_ld")
    assert r.draft.title == "Data Engineer"
    assert r.draft.company == "Example"
    assert r.draft.sourceUrl == URL and r.providerCalls == browser.called == 0
    assert r.diagnostics.descriptionLength == len(r.draft.description)


def test_static_job_does_not_infer_company_from_site_brand_or_navigation():
    browser = Browser(AssertionError("static pages should not launch Chromium"))
    html = '<nav>推荐岗位</nav><footer>隐私协议</footer>' + STATIC
    result = capture(Http(html), browser)
    assert (result.status, result.extractionMethod) == ("captured", "static_html")
    assert "推荐岗位" not in result.draft.description
    no_company = html.replace('data-company-name="Example"', '') + '<meta property="og:site_name" content="JobBoard">'
    result = capture(Http(no_company), browser)
    assert result.status == "failed" and result.draft is None


GREENHOUSE_URL = "https://job-boards.greenhouse.io/example/jobs/12345-67"
GREENHOUSE_TITLE = "Engineer at Scale"


def greenhouse_html(page_title, *, company="", structured=""):
    return (
        f"<title>{page_title}</title>{structured}<main>"
        f'<div class="job__header"><h1>{GREENHOUSE_TITLE}</h1></div>'
        f'{company}<div class="job__description"><p>{JD}</p></div>'
        "<section><h2>Application instructions</h2><p>Not part of the description.</p></section>"
        "</main>"
    )


def test_greenhouse_title_identifies_employer_and_limits_job_description():
    html = greenhouse_html(f"Job Application for {GREENHOUSE_TITLE} at Example Hiring Co")
    browser = Browser(AssertionError("static posting should not start Chromium"))
    result = capture(Http(html, url=GREENHOUSE_URL), browser)
    assert (result.status, result.extractionMethod, result.qualityGrade) == ("captured", "static_html", "full_jd")
    assert result.draft.title == GREENHOUSE_TITLE
    assert result.draft.company == "Example Hiring Co"
    assert result.draft.description == JD.strip()


@pytest.mark.parametrize(("url", "page_title"), [
    (URL, f"Job Application for {GREENHOUSE_TITLE} at Example Hiring Co"),
    (GREENHOUSE_URL, "Job Application for Other Engineer at Example Hiring Co"),
    (GREENHOUSE_URL, f"Job Application for {GREENHOUSE_TITLE} at "),
    (GREENHOUSE_URL, f"{GREENHOUSE_TITLE} | Greenhouse"),
])
def test_greenhouse_does_not_guess_unconfirmed_employer(url, page_title):
    result = capture(Http(greenhouse_html(page_title), url=url), Browser(AssertionError("not an SPA")))
    assert result.status == "failed" and result.draft is None


def test_greenhouse_preserves_explicit_and_structured_employer_evidence():
    page_title = f"Job Application for {GREENHOUSE_TITLE} at Page Company"
    browser = Browser(AssertionError("static posting should not start Chromium"))
    labeled = greenhouse_html(page_title, company='<span data-company-name="Labeled Company"></span>')
    result = capture(Http(labeled, url=GREENHOUSE_URL), browser)
    assert result.draft.company == "Labeled Company"
    data = {"@type": "JobPosting", "title": GREENHOUSE_TITLE,
            "hiringOrganization": {"name": "Structured Company"}, "description": "Short description."}
    markup = greenhouse_html(page_title, structured=f'<script type="application/ld+json">{json.dumps(data)}</script>')
    result = capture(Http(markup, url=GREENHOUSE_URL), browser)
    assert result.extractionMethod == "static_html"
    assert result.draft.company == "Structured Company"


@pytest.mark.parametrize(("page", "status", "final", "reason"), [
    (SHELL, 200, URL.replace("/a", "/login"), "login_required"),
    ("<title>验证码</title>" + STATIC, 200, URL, "captcha_detected"),
    (SHELL, 401, URL, "login_required"),
    (SHELL, 403, URL, "anti_bot_challenge"),
    (SHELL, 429, URL, "anti_bot_challenge"),
    ('<title>Security Verification</title><main id="app"><h1>Security Verification</h1></main>'
     '<footer>Protected by Tencent Cloud EdgeOne</footer><script src="/widget.js"></script>',
     200, "https://www.zhaopin.com/jobdetail/CC123J456.htm", "anti_bot_challenge"),
    ('<meta name="aliyun_waf_aa"><div id="renderData"></div><script src="/widget.js"></script>',
     200, "https://jobs.51job.com/example/123.html", "anti_bot_challenge"),
    ('<meta name="aliyun_waf_aa"><div id="renderData"></div><script src="/widget.js"></script>',
     200, "https://msearch.51job.com/jobs/example/123.html", "anti_bot_challenge"),
    ('<main>为了更好的访问体验，请进行验证</main><script src="/widget.js"></script>',
     200, "https://jobs.51job.com/example/123.html", "anti_bot_challenge"),
    (SHELL, 200, "https://safe.liepin.com/page/liepin/captchaPage_ip_PC", "captcha_detected"),
])
def test_intervention_stops_before_browser(page, status, final, reason):
    browser = Browser(AssertionError("must not try a restricted page again"))
    result = capture(Http(page, status, url=final), browser, renderMode="playwright")
    assert result.status == "needs_human_intervention" and result.interventionReason == reason
    assert result.draft is None and result.providerCalls == browser.called == 0
    assert result.diagnostics.adapterUsed == "guarded_http"


LIEPIN_URL = "https://www.liepin.com/job/123.shtml"
CHINESE_JD = "岗位职责：" + "维护集成服务并编写回归测试，整理上线记录并和团队核对。 " * 10
CHINESE_POSTING = '<script type="application/ld+json">' + json.dumps({
    "@type": "JobPosting", "title": "应用开发工程师",
    "hiringOrganization": {"name": "示例软件公司"}, "description": CHINESE_JD,
}) + '</script>'
PAUSED_POSTING = '<span class="apply-stop-title">该职位已暂停招聘</span>' + STATIC + CHINESE_POSTING


@pytest.mark.parametrize("rendered", [False, True])
def test_liepin_paused_posting_never_captures_recommendations_or_stale_metadata(rendered):
    browser = Browser(RenderedPage(PAUSED_POSTING, "") if rendered else AssertionError("paused page is terminal"))
    result = capture(Http(SHELL if rendered else PAUSED_POSTING, url=LIEPIN_URL), browser)
    assert (result.status, result.blockers) == ("failed", ["posting_inactive"])
    assert result.draft is None and result.providerCalls == 0
    assert browser.called == int(rendered)


@pytest.mark.parametrize(("url", "other_content"), [
    (LIEPIN_URL, "<aside>推荐岗位：该职位已暂停招聘</aside>"),
    (URL, '<span class="apply-stop-title">该职位已暂停招聘</span>'),
    ("https://www.liepin.com/company/123.shtml", '<span class="apply-stop-title">该职位已暂停招聘</span>'),
    ("https://safe.liepin.com.example.test/page/liepin/captchaPage_ip_PC", ""),
    ("https://jobs.51job.com/example/123.html", '<div id="renderData"></div>'),
    ("https://jobs.51job.com/example/123.html", "为了更好的访问体验，请进行验证"),
    ("https://jobs.51job.com.example.test/example/123.html", '<meta name="aliyun_waf_aa"><div id="renderData"></div>'),
    ("https://www.zhaopin.com/jobdetail/CC123J456.htm", "<title>Security Verification Engineer</title>"),
    ("https://www.zhaopin.com/jobdetail/CC123J456.htm", "<title>Security Verification</title>"),
])
def test_domestic_public_job_is_not_mistaken_for_an_interstitial_or_paused_listing(url, other_content):
    html = other_content + CHINESE_POSTING
    browser = Browser(AssertionError("structured fast path must not start browser"))
    result = capture(Http(html, url=url), browser)
    assert (result.status, result.extractionMethod, result.qualityGrade) == ("captured", "json_ld", "full_jd")
    assert (result.draft.title, result.draft.company) == ("应用开发工程师", "示例软件公司")
    assert result.draft.sourceUrl == url and browser.called == 0


def test_spa_falls_back_to_dom_and_forced_mode_skips_fast_result():
    browser = Browser(RenderedPage(STATIC, ""))
    for page, mode in [(SHELL, "auto"), (STATIC, "playwright")]:
        result = capture(Http(page), browser, renderMode=mode)
        assert result.status == "captured" and result.extractionMethod == "playwright_dom"
    assert browser.called == 2


def test_a11y_fallback_has_only_semantic_content():
    page = '<h1>Engineer</h1><div class="company-name">Example</div>'
    snapshot = f'- main:\n  - heading "Engineer" [level=1]\n  - navigation:\n    - text: Recommended jobs\n  - paragraph: {JD}'
    result = capture(Http(SHELL), Browser(RenderedPage(page, snapshot)))
    assert result.extractionMethod == "playwright_a11y"
    assert result.draft.description == JD.strip() and result.diagnostics.a11yNodeCount == 5


def test_empty_spa_and_missing_chromium_give_actionable_result():
    r = capture(Http(SHELL), Browser(RenderedPage(SHELL, "")))
    assert r.status == "needs_human_intervention" and r.interventionReason == "unsupported_spa_shell"
    for reason in ("playwright_not_installed", "browser_isolation_unavailable", "capture_budget_exceeded"):
        r = capture(Http(SHELL), Browser(CaptureError(reason)))
        assert r.status == "failed" and r.blockers == [reason] and r.draft is None


@pytest.mark.parametrize(("text", "grade"), [
    ("", "unavailable"), ("x" * 39, "card_only"), ("x" * 40, "partial_jd"),
    ("Responsibilities:" + "x" * 162, "partial_jd"), ("Responsibilities:" + "x" * 163, "full_jd"),
    ("x" * 180, "partial_jd"),
])
def test_quality_boundaries(text, grade):
    assert grade_description(text) == grade


def test_truncation_diagnostics_reflect_actual_draft():
    r = capture(Http(STATIC.replace(JD, "Requirements: " + "字" * 52_000)), Browser(AssertionError))
    assert r.diagnostics.truncationApplied
    assert r.diagnostics.rawTextLength > r.diagnostics.descriptionLength == len(r.draft.description) == 50_000


def test_deadline_cancels_in_flight_fetch():
    class Slow:
        cancelled = False

        async def fetch(self, *_args):
            try:
                await asyncio.sleep(10)
            finally:
                self.cancelled = True

    async def exercise():
        http = Slow()
        use_case = CaptureJobUrlUseCase(http)
        # Public minimum stays 3s; use a constructed request to avoid 3s in the unit suite.
        request = UrlJobCaptureRequest.model_construct(url=URL, renderMode="auto", timeoutMs=30)
        start = time.monotonic()
        result = await use_case.execute(request)
        assert time.monotonic() - start < 0.5
        await asyncio.sleep(0)
        assert http.cancelled and result.blockers == ["capture_timeout"] and result.draft is None
    asyncio.run(exercise())


def test_playwright_import_is_optional(monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, "playwright", None)
    monkeypatch.delitem(sys.modules, "playwright.async_api", raising=False)
    r = capture(Http(SHELL), PlaywrightFetcher())
    assert r.blockers == ["playwright_not_installed"]
    assert capture(Http(STATIC), PlaywrightFetcher()).status == "captured"

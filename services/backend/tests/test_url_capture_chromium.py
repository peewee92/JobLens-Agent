"""Opt-in real Chromium replay. All upstream responses are synthetic and offline."""
import asyncio
import json
import os

import pytest

from app.application.url_capture.models import UrlJobCaptureRequest
from app.application.url_capture.ssrf_guard import GuardedHttpClient, PageResponse
from app.application.url_capture.use_case import CaptureJobUrlUseCase

pytestmark = pytest.mark.skipif(
    os.environ.get("JOBLENS_TEST_CHROMIUM") != "1",
    reason="opt in after installing Playwright and Chromium",
)
URL = "https://job.test/"
JD = "Responsibilities: " + "Build test tools and explain decisions to your teammates. " * 5


def response(url, kind, content):
    return PageResponse(str(url), 200, {"content-type": kind}, content.encode())


async def resolve(host, _):
    assert host == "job.test", f"unexpected upstream: {host}"
    return ["93.184.216.34"]


def test_real_chromium_fulfills_script_and_fetch_without_direct_connections():
    async def exercise():
        witness_connections = []
        proxy_calls = []

        def witness(_reader, writer):
            witness_connections.append(True)
            writer.close()

        async with await asyncio.start_server(witness, "127.0.0.1", 0) as listener:
            port = listener.sockets[0].getsockname()[1]
            async def upstream(url, address, budget):
                assert address == "93.184.216.34"
                proxy_calls.append(url.path)
                if url.path == "/":
                    result = response(url, "text/html", f"""
                        <main id="app"></main><script src="/job.js"></script>
                        <script src="https://other.test/third-party.js"></script>
                        <img src="/image"><img src="http://127.0.0.1:{port}/image">
                        <link rel="stylesheet" href="/style">
                        <link rel="preconnect" href="http://127.0.0.1:{port}">
                    """)
                elif url.path == "/job.js":
                    result = response(url, "application/javascript", f"""
                        try {{ new WebSocket("ws://127.0.0.1:{port}/socket") }} catch {{}}
                        fetch("/write", {{method:"POST",body:"must not be sent"}}).catch(() => {{}});
                        fetch("/data").then(r => r.json()).then(data => {{
                          document.getElementById("app").innerHTML =
                            '<h1>Engineer</h1><div data-company-name="Example"></div><section class="job-description"></section>';
                          document.querySelector(".job-description").textContent = data.jd;
                        }});
                    """)
                elif url.path == "/data":
                    result = response(url, "application/json", json.dumps({"jd": JD}))
                else:
                    pytest.fail(f"outbound request should not be made: {url.path}")
                budget.consume_bytes(len(result.body))
                return result

            r = await CaptureJobUrlUseCase(GuardedHttpClient(resolve, upstream)).execute(UrlJobCaptureRequest(url=URL))
            await asyncio.sleep(0.05)
            assert not witness_connections
        assert (r.status, r.extractionMethod) == ("captured", "playwright_dom"), r.model_dump()
        assert r.draft.description == JD.strip() and r.providerCalls == 0
        assert proxy_calls == ["/", "/job.js", "/data"]

    asyncio.run(exercise())


@pytest.mark.parametrize(("path", "expected"), [
    ("/private-redirect", "url_capture_ssrf_blocked"),
    ("/too-many", "capture_budget_exceeded"),
    ("/slow", "capture_timeout"),
])
def test_real_chromium_fatal_resource_errors_discard_draft_and_cancel_egress(path, expected, monkeypatch):
    from app.application.url_capture import ssrf_guard

    if path == "/too-many":
        monkeypatch.setattr(ssrf_guard, "MAX_SUBREQUESTS", 1)

    async def exercise():
        entered, cancelled = asyncio.Event(), asyncio.Event()
        calls = []

        async def upstream(url, _address, _budget):
            calls.append(url.path)
            if url.path == "/":
                script = "/slow" if path == "/slow" else "/job.js"
                return response(url, "text/html", f'<main id="app"></main><script src="{script}"></script>')
            if url.path == "/job.js":
                return response(url, "application/javascript", f'''
                    document.querySelector("main").innerHTML = `<h1>Engineer</h1><span class="company-name">Example</span>
                      <div class="job-description">{JD}</div>`;
                    fetch("{path}").catch(() => {{}});
                ''')
            assert url.path == path
            if path == "/private-redirect":
                return PageResponse(str(url), 302, {"location": "http://127.0.0.1/"}, b"")
            if path == "/slow":
                entered.set()
                try:
                    await asyncio.sleep(60)
                finally:
                    cancelled.set()
            pytest.fail("subrequest should not have a connection after the cap")

        request = UrlJobCaptureRequest(url=URL, timeoutMs=3000 if path == "/slow" else 15000)
        result = await CaptureJobUrlUseCase(GuardedHttpClient(resolve, upstream)).execute(request)
        assert result.draft is None and result.blockers == [expected], result.model_dump()
        if path == "/slow":
            assert entered.is_set()
            await asyncio.wait_for(cancelled.wait(), 1)
        if path == "/too-many":
            assert calls == ["/", "/job.js"]

    asyncio.run(exercise())

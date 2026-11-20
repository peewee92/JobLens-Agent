"""Local Chromium adapter. Chromium never performs any intentional upstream fetch."""
from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass
import os

from .html_extractor import url_intervention
from .models import InterventionReason
from .ssrf_guard import CaptureBudget, CaptureError, GuardedHttpClient, PageResponse, origin, parse_url

ALLOWED_RESOURCE_TYPES = frozenset({"document", "script", "xhr", "fetch"})
CHROMIUM_ARGS = (
    "--disable-background-networking",
    "--disable-quic",
    "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1",
    "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
)
_BROWSER_ENV = (
    "PATH", "HOME", "TMPDIR", "TMP", "TEMP", "LANG", "LC_ALL",
    "SYSTEMROOT", "WINDIR", "USERPROFILE", "APPDATA", "LOCALAPPDATA",
)


@dataclass(frozen=True)
class RenderedPage:
    html: str
    accessibility: str


class RenderIntervention(Exception):
    def __init__(self, reason: InterventionReason) -> None:
        self.reason = reason


def intervention_for_status(status: int) -> InterventionReason | None:
    if status == 401:
        return "login_required"
    if status in {403, 429}:
        return "anti_bot_challenge"
    return None


def fulfill_headers(response: PageResponse) -> dict[str, str]:
    # Never pass redirects, cookies, refresh, link/prefetch or authentication headers back to Chromium.
    return ({
        key: value for key, value in response.headers.items()
        if key in {"content-type", "content-security-policy"}
    } | {"referrer-policy": "no-referrer"})


class DenyProxy:
    """A real, bound loopback listener that never opens a connection to any destination."""
    def __init__(self):
        self.attempted = asyncio.Event()

    async def __aenter__(self):
        self.server = await asyncio.start_server(self._reject, "127.0.0.1", 0)
        self.url = f"http://127.0.0.1:{self.server.sockets[0].getsockname()[1]}"
        return self

    def _reject(self, _reader, writer):
        self.attempted.set()
        writer.close()

    async def __aexit__(self, *_):
        self.server.close()
        await self.server.wait_closed()


async def verify_proxy(browser, proxy: DenyProxy, playwright_error) -> None:
    """Probe loopback proxying before handling page-controlled code."""
    contacted = False

    def witness(_reader, writer):
        nonlocal contacted
        contacted = True
        writer.close()

    async with await asyncio.start_server(witness, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        tab = await browser.new_page()
        try:
            proxy.attempted.clear()
            with suppress(playwright_error):
                await tab.goto(f"http://127.0.0.1:{port}/", timeout=1000)
            if contacted or not proxy.attempted.is_set():
                raise CaptureError("browser_isolation_unavailable")
        finally:
            await tab.close()


class PlaywrightFetcher:
    async def render(self, document: PageResponse, client: GuardedHttpClient, budget: CaptureBudget) -> RenderedPage:
        try:
            from playwright.async_api import Error, TimeoutError as PlaywrightTimeout, async_playwright
        except ImportError as exc:
            raise CaptureError("playwright_not_installed") from exc

        try:
            async with DenyProxy() as deny, async_playwright() as playwright:
                try:
                    browser = await playwright.chromium.launch(
                        chromium_sandbox=True,
                        proxy={"server": deny.url, "bypass": "<-loopback>"},
                        args=list(CHROMIUM_ARGS),
                        ignore_default_args=["--disable-popup-blocking"],
                        env={key: os.environ[key] for key in _BROWSER_ENV if key in os.environ},
                    )
                except Error as exc:
                    code = "playwright_not_installed" if "executable doesn't exist" in str(exc).lower() else "browser_isolation_unavailable"
                    raise CaptureError(code) from exc
                try:
                    await verify_proxy(browser, deny, Error)
                    return await self._render_document(browser, document, client, budget, Error, PlaywrightTimeout)
                finally:
                    with suppress(Error):
                        await browser.close()
        except (OSError, Error) as exc:
            raise CaptureError("browser_isolation_unavailable") from exc

    async def _render_document(self, browser, document, client, budget, playwright_error, playwright_timeout):
        context = await browser.new_context(accept_downloads=False, service_workers="block")
        page = await context.new_page()
        initial_url = parse_url(document.url)
        initial_origin = origin(initial_url)
        fatal_result: asyncio.Future[CaptureError | RenderIntervention] = asyncio.get_running_loop().create_future()
        pending: set[asyncio.Task] = set()
        stopping = False
        served_document = False

        async def handle(route):
            nonlocal stopping, served_document
            task = asyncio.current_task()
            pending.add(task)
            try:
                request = route.request
                if stopping or budget.closed or request.method != "GET" or request.resource_type not in ALLOWED_RESOURCE_TYPES:
                    await route.abort()
                    return
                if request.resource_type == "document":
                    if not served_document and request.frame == page.main_frame and parse_url(request.url) == initial_url:
                        served_document = True
                        response = document
                    else:
                        if request.frame == page.main_frame and (reason := url_intervention(request.url)):
                            raise RenderIntervention(reason)
                        await route.abort()
                        return
                else:
                    response = await client.fetch(request.url, budget, same_origin=initial_origin)
                    if reason := intervention_for_status(response.status):
                        raise RenderIntervention(reason)
                if stopping or budget.closed:
                    await route.abort()
                else:
                    await route.fulfill(status=response.status, headers=fulfill_headers(response), body=response.body)
            except (CaptureError, RenderIntervention) as exc:
                if (isinstance(exc, RenderIntervention) or exc.code in {
                    "url_capture_ssrf_blocked", "capture_budget_exceeded", "response_too_large",
                }) and not fatal_result.done():
                    stopping = True
                    budget.closed = True
                    fatal_result.set_result(exc)
                with suppress(playwright_error):
                    await route.abort()
            except (ValueError, playwright_error):
                with suppress(playwright_error):
                    await route.abort()
            finally:
                pending.discard(task)

        async def reject_socket(websocket):
            await websocket.close()

        async def read_page():
            await page.goto(document.url, wait_until="domcontentloaded", timeout=0)
            with suppress(playwright_timeout):
                await page.wait_for_load_state("networkidle", timeout=2500)
            html = await page.evaluate("() => document.documentElement.outerHTML.slice(0, 2000000)")
            snapshot = ""
            with suppress(playwright_timeout):
                snapshot = (await page.aria_snapshot(depth=12, timeout=400))[:100_000]
            return RenderedPage(html, snapshot)

        render_task = None
        try:
            await context.route("**/*", handle)
            await context.route_web_socket("**/*", reject_socket)
            render_task = asyncio.create_task(read_page())
            await asyncio.wait({render_task, fatal_result}, return_when=asyncio.FIRST_COMPLETED)
            if fatal_result.done():
                raise fatal_result.result()
            if not served_document:
                raise CaptureError("browser_isolation_unavailable")
            try:
                return render_task.result()
            except playwright_error as exc:
                raise CaptureError("browser_render_failed") from exc
        finally:
            stopping = True
            if render_task is not None:
                render_task.cancel()
            active = list(pending) + ([render_task] if render_task else [])
            for task in active:
                task.cancel()
            if active:
                await asyncio.gather(*active, return_exceptions=True)
            fatal_result.cancel()
            with suppress(playwright_error):
                await context.close()

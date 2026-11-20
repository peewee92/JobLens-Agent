import asyncio
import os

import httpcore
import pytest

from app.application.url_capture import ssrf_guard as guard


@pytest.mark.parametrize("host", [
    "127.0.0.1", "localhost", "LOCALHOST.", "169.254.169.254", "10.0.0.1", "100.64.0.1",
    "192.168.1.1", "172.16.0.1", "0.0.0.0", "239.1.0.1", "[::1]", "[::ffff:127.0.0.1]",
    "[fc00::1]", "[fe80::1]", "[64:ff9b::7f00:1]",
])
def test_private_and_special_addresses_fail_before_connection(host):
    async def never(*_):
        pytest.fail("literal address must not be resolved or connected")
    with pytest.raises(guard.CaptureError, match="url_capture_ssrf_blocked"):
        asyncio.run(guard.GuardedHttpClient(never, never).fetch(f"http://{host}/", guard.CaptureBudget()))


@pytest.mark.parametrize("url", ["file:///private/file", "https://user:secret@host.test/", "https://host.test:9999/"])
def test_forbidden_protocol_credentials_and_port(url):
    async def never(*_):
        pytest.fail("policy check must precede network")
    with pytest.raises(guard.CaptureError, match="url_capture_policy_blocked"):
        asyncio.run(guard.GuardedHttpClient(never, never).fetch(url, guard.CaptureBudget()))


def test_mixed_dns_answers_fail_closed():
    async def resolve(*_):
        return ["93.184.216.34", "169.254.169.254"]
    async def never(*_):
        pytest.fail("mixed DNS result must not connect")
    with pytest.raises(guard.CaptureError, match="url_capture_ssrf_blocked"):
        asyncio.run(guard.GuardedHttpClient(resolve, never).fetch("https://job.test", guard.CaptureBudget()))


@pytest.mark.parametrize("target", ["/same-host-rebinding", "http://127.0.0.1/forbidden"])
def test_each_redirect_checked_even_for_same_host(target):
    answers = iter([["93.184.216.34"], ["127.0.0.1"]])
    hops = []
    async def resolve(*_):
        return next(answers)
    async def get(url, address, _budget):
        hops.append((str(url), address))
        return guard.PageResponse(str(url), 302, {"location": target}, b"")
    with pytest.raises(guard.CaptureError, match="url_capture_ssrf_blocked"):
        asyncio.run(guard.GuardedHttpClient(resolve, get).fetch("https://job.test/role", guard.CaptureBudget()))
    assert hops == [("https://job.test/role", "93.184.216.34")]


def test_browser_subrequests_and_redirects_share_request_budget(monkeypatch):
    monkeypatch.setattr(guard, "MAX_SUBREQUESTS", 2)
    calls = []
    async def resolve(*_):
        return ["93.184.216.34"]
    async def get(url, _address, _budget):
        calls.append(url.path)
        return guard.PageResponse(str(url), 302, {"location": f"/hop{len(calls)}"}, b"")
    async def run():
        budget = guard.CaptureBudget()
        page = guard.parse_url("https://job.test/")
        await guard.GuardedHttpClient(resolve, get).fetch(str(page), budget, same_origin=guard.origin(page))
    with pytest.raises(guard.CaptureError, match="capture_budget_exceeded"):
        asyncio.run(run())
    assert calls == ["/", "/hop1"]


def test_cross_origin_resource_redirect_never_resolves_target():
    async def resolve(host, _port):
        assert host == "job.test"
        return ["93.184.216.34"]
    async def get(url, _address, _budget):
        assert url.host == "job.test"
        return guard.PageResponse(str(url), 302, {"location": "https://other.test/file.js"}, b"")
    with pytest.raises(guard.CaptureError, match="cross_origin_resource"):
        asyncio.run(guard.GuardedHttpClient(resolve, get).fetch(
            "https://job.test/script.js", guard.CaptureBudget(), same_origin=guard.origin(guard.parse_url("https://job.test/")),
        ))


def test_transport_connects_only_to_pinned_ip_and_retains_tls_hostname(monkeypatch):
    requests = []
    class Stream(httpcore.AsyncNetworkStream):
        async def start_tls(self, ssl_context, server_hostname=None, timeout=None):
            requests.append(("tls", server_hostname, ssl_context.check_hostname))
            return self

        async def write(self, buffer, timeout=None):
            requests.append(("request", buffer))

        async def read(self, max_bytes, timeout=None):
            return b"HTTP/1.1 200 OK\r\nContent-Length: 5\r\nContent-Type: text/html\r\n\r\nhello"

        async def aclose(self):
            pass

        def get_extra_info(self, _info):
            return None

    async def connect(_self, host, port, *_args, **_kwargs):
        requests.append(("connect", host, port))
        return Stream()
    monkeypatch.setattr(httpcore.AnyIOBackend, "connect_tcp", connect)
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:3456")
    budget = guard.CaptureBudget()
    result = asyncio.run(guard.get_pinned(guard.parse_url("https://listing.test/engineer"), "93.184.216.34", budget))
    assert requests[:2] == [("connect", "93.184.216.34", 443), ("tls", "listing.test", True)]
    assert b"Host: listing.test" in requests[2][1]
    assert result.body == b"hello" and budget.downloaded == 5


def test_download_budget_and_closed_gate(monkeypatch):
    monkeypatch.setattr(guard, "MAX_DOWNLOAD_BYTES", 5)
    budget = guard.CaptureBudget()
    budget.consume_bytes(2)
    budget.consume_bytes(3)
    with pytest.raises(guard.CaptureError, match="capture_budget_exceeded"):
        budget.consume_bytes(1)
    budget.closed = True
    with pytest.raises(guard.CaptureError, match="capture_budget_exceeded"):
        budget.consume_request(resource=False)

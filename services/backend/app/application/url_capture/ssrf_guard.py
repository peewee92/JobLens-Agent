"""One GET-only transport for documents and rendered resources."""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from ipaddress import IPv6Address, ip_address, ip_network
import re
import socket
from urllib.parse import urljoin, urlsplit

import httpcore
import httpx

MAX_URL_CHARS = 2048
MAX_BODY_BYTES = 2_000_000
MAX_DOWNLOAD_BYTES = 5_000_000
MAX_SUBREQUESTS = 25
MAX_REDIRECTS = 5
REDIRECTS = {301, 302, 303, 307, 308}
DEFAULT_PORTS = {"http": 80, "https": 443}
TRANSITION_NETWORKS = tuple(map(ip_network, ("64:ff9b::/96", "64:ff9b:1::/48", "2002::/16", "2001::/32")))


class CaptureError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def parse_url(raw: str) -> httpx.URL:
    """Use one canonical URL for policy, origin checks, and the actual request."""
    if len(raw) > MAX_URL_CHARS or not re.match(r"^https?://", raw) or re.search(r"[\s\\\x00-\x1f\x7f]", raw):
        raise ValueError("expected an absolute HTTP(S) URL")
    try:
        parts = urlsplit(raw)
        host = parts.hostname
        port = parts.port
        parsed = httpx.URL(raw)
    except (ValueError, httpx.InvalidURL) as exc:
        raise ValueError("invalid HTTP(S) URL") from exc
    if (not host or not parsed.raw_host or "%" in host
            or (port is not None and not 1 <= port <= 65535)
            or len(str(parsed)) > MAX_URL_CHARS):
        raise ValueError("invalid HTTP(S) URL")
    # Preserve even empty userinfo for policy checks; never let URL canonicalization erase it.
    if "@" in parts.netloc:
        raise CaptureError("url_capture_policy_blocked")
    return parsed.copy_with(fragment=None)


def origin(url: httpx.URL) -> tuple[str, bytes, int]:
    return url.scheme, url.raw_host, url.port or DEFAULT_PORTS[url.scheme]


def checked_address(value: str) -> str:
    try:
        address = ip_address(value)
    except ValueError as exc:
        raise CaptureError("url_capture_ssrf_blocked") from exc
    if isinstance(address, IPv6Address):
        if address.scope_id or address.ipv4_mapped is not None or address.is_site_local or any(address in net for net in TRANSITION_NETWORKS):
            raise CaptureError("url_capture_ssrf_blocked")
    if not address.is_global or address.is_multicast or address.is_reserved:
        raise CaptureError("url_capture_ssrf_blocked")
    return str(address)


def check_literal(url: httpx.URL) -> str | None:
    host = url.raw_host.decode("ascii").removesuffix(".")
    if host == "localhost" or host.endswith(".localhost"):
        raise CaptureError("url_capture_ssrf_blocked")
    try:
        ip_address(host)
    except ValueError:
        return None
    return checked_address(host)


async def resolve_host(host: str, port: int) -> list[str]:
    answers = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP)
    return [answer[4][0] for answer in answers]


async def checked_addresses(url: httpx.URL, resolve: Callable[[str, int], Awaitable[list[str]]]) -> tuple[str, ...]:
    scheme, host, port = origin(url)
    if port != DEFAULT_PORTS[scheme]:
        raise CaptureError("url_capture_policy_blocked")
    literal = check_literal(url)
    if literal is not None:
        return (literal,)
    try:
        answers = await resolve(host.decode("ascii"), port)
    except OSError as exc:
        raise CaptureError("dns_failed") from exc
    if not answers:
        raise CaptureError("dns_failed")
    return tuple(dict.fromkeys(checked_address(answer) for answer in answers))


class PinnedNetwork(httpcore.AnyIOBackend):
    """Connect to a numeric IP, but leave HTTP authority and TLS SNI with HTTPCore."""
    def __init__(self, hostname: str, port: int, address: str) -> None:
        self.hostname, self.port, self.address = hostname, port, address

    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        if (host, port) != (self.hostname, self.port):
            raise CaptureError("url_capture_policy_blocked")
        return await super().connect_tcp(self.address, port, timeout, local_address, socket_options)

    async def connect_unix_socket(self, *args, **kwargs):
        raise CaptureError("url_capture_policy_blocked")


@dataclass
class CaptureBudget:
    downloaded: int = 0
    subrequests: int = 0
    closed: bool = False

    def consume_request(self, *, resource: bool) -> None:
        if self.closed or (resource and self.subrequests >= MAX_SUBREQUESTS):
            raise CaptureError("capture_budget_exceeded")
        self.subrequests += int(resource)

    def consume_bytes(self, size: int) -> None:
        if self.closed or self.downloaded + size > MAX_DOWNLOAD_BYTES:
            raise CaptureError("capture_budget_exceeded")
        self.downloaded += size


@dataclass(frozen=True)
class PageResponse:
    url: str
    status: int
    headers: dict[str, str]
    body: bytes

    @property
    def is_html(self) -> bool:
        return self.headers.get("content-type", "").partition(";")[0].strip().lower() in {
            "text/html", "application/xhtml+xml",
        }


async def get_pinned(url: httpx.URL, address: str, budget: CaptureBudget) -> PageResponse:
    _, host, port = origin(url)
    backend = PinnedNetwork(host.decode("ascii"), port, address)
    # One connection per hop: a pooled connection cannot defeat fresh DNS validation.
    async with httpcore.AsyncConnectionPool(network_backend=backend, max_keepalive_connections=0) as pool:
        async with pool.stream(
            "GET", str(url),
            headers={"User-Agent": "JobLens-URL-Capture/1.0", "Accept": "*/*", "Accept-Encoding": "identity"},
        ) as response:
            headers = {
                key.decode("ascii").lower(): value.decode("latin-1")
                for key, value in response.headers
                if key.lower() in {b"location", b"content-type", b"content-encoding", b"content-security-policy", b"content-length"}
            }
            body = bytearray()
            if 200 <= response.status < 300:
                # Never expand compressed, attacker-controlled data. Advertise identity only.
                if headers.get("content-encoding", "identity").strip().lower() != "identity":
                    raise CaptureError("unsupported_content_encoding")
                async for chunk in response.aiter_stream():
                    budget.consume_bytes(len(chunk))
                    if len(body) + len(chunk) > MAX_BODY_BYTES:
                        raise CaptureError("response_too_large")
                    body.extend(chunk)
            return PageResponse(str(url), response.status, headers, bytes(body))


class GuardedHttpClient:
    def __init__(self, resolver=resolve_host, get=get_pinned) -> None:
        self._resolver = resolver
        self._get = get

    async def fetch(
        self, raw: str, budget: CaptureBudget, *, same_origin: tuple[str, bytes, int] | None = None,
    ) -> PageResponse:
        for hop in range(MAX_REDIRECTS + 1):
            try:
                url = parse_url(raw)
            except ValueError as exc:
                raise CaptureError("url_capture_policy_blocked") from exc
            if same_origin is not None:
                check_literal(url)
                if origin(url) != same_origin:
                    raise CaptureError("cross_origin_resource")
            budget.consume_request(resource=same_origin is not None)
            addresses = await checked_addresses(url, self._resolver)
            if budget.closed:
                raise CaptureError("capture_budget_exceeded")
            # Prefer IPv4 for local installations without IPv6 routing. All DNS
            # answers have already passed validation, including unused answers.
            address = min(addresses, key=lambda item: ip_address(item).version)
            try:
                response = await self._get(url, address, budget)
            except (OSError, httpcore.NetworkError, httpcore.ProtocolError, httpcore.TimeoutException) as exc:
                raise CaptureError("network_error") from exc
            if response.status not in REDIRECTS:
                return response
            location = response.headers.get("location")
            if not location:
                raise CaptureError("invalid_redirect")
            if hop == MAX_REDIRECTS:
                raise CaptureError("too_many_redirects")
            raw = urljoin(str(url), location)
        raise AssertionError("redirect loop did not terminate")

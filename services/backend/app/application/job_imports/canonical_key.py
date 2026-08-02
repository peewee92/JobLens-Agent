"""Deterministic source identity and canonical-key helpers."""
from __future__ import annotations

import hashlib
import re
import unicodedata
from urllib.parse import quote, urlsplit, urlunsplit

from app.application.job_imports.errors import CanonicalIdentityError

CANONICAL_KEY_VERSION = "v1"
_BOSS_SOURCE = "boss"
_BOSS_JOB_PATH = re.compile(r"^/job_detail/(?P<job_id>[^/]+?)(?:\.html)?$", re.IGNORECASE)


def normalize_source_name(source: str) -> str:
    """Normalize an internal source namespace such as ``boss``."""

    value = unicodedata.normalize("NFKC", source).strip().casefold()
    value = re.sub(r"[^a-z0-9.-]+", "-", value).strip("-")
    if not value:
        raise CanonicalIdentityError("source name is empty after normalization")
    return value


def normalize_external_id(source_job_id: str | None) -> str | None:
    """Trim an opaque external ID without changing its case or semantics."""

    if source_job_id is None:
        return None
    value = unicodedata.normalize("NFKC", source_job_id).strip()
    return value or None


def normalize_source_url(source_url: str, *, source: str) -> str:
    """Normalize a source URL for identity comparison.

    For BOSS URLs we remove tracking query/fragment values, canonicalize all
    zhipin.com subdomains to ``www.zhipin.com``, and use HTTPS. Opaque path
    characters keep their original case because job IDs may be case-sensitive.
    """

    raw_url = source_url.strip()
    if not raw_url:
        raise CanonicalIdentityError("source URL is empty")

    try:
        parts = urlsplit(raw_url)
        hostname = parts.hostname
        port = parts.port
    except ValueError as error:
        raise CanonicalIdentityError(f"invalid source URL: {raw_url}") from error

    if parts.scheme.casefold() not in {"http", "https"} or not hostname:
        raise CanonicalIdentityError("source URL must be an absolute HTTP(S) URL")
    if parts.username or parts.password:
        raise CanonicalIdentityError("source URL must not contain user credentials")

    normalized_source = normalize_source_name(source)
    scheme = parts.scheme.casefold()
    host = hostname.casefold().rstrip(".")

    if normalized_source == _BOSS_SOURCE:
        if host != "zhipin.com" and not host.endswith(".zhipin.com"):
            raise CanonicalIdentityError("BOSS source URL must use a zhipin.com host")
        scheme = "https"
        host = "www.zhipin.com"
        port = None

    netloc = host
    if port is not None and not (
        (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    ):
        netloc = f"{host}:{port}"

    path = re.sub(r"/{2,}", "/", parts.path or "/")
    if path != "/":
        path = path.rstrip("/")

    return urlunsplit((scheme, netloc, path, "", ""))


def extract_source_job_id(normalized_source_url: str, *, source: str) -> str | None:
    """Extract a platform job ID when the source URL exposes one."""

    normalized_source = normalize_source_name(source)
    if normalized_source != _BOSS_SOURCE:
        return None

    path = urlsplit(normalized_source_url).path
    match = _BOSS_JOB_PATH.fullmatch(path)
    if not match:
        return None
    return normalize_external_id(match.group("job_id"))


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normalize_fingerprint_text(value: str | None) -> str:
    if value is None:
        return ""
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"\s+", " ", normalized).strip()


def build_canonical_key(
    *,
    source: str,
    source_job_id: str | None,
    normalized_source_url: str | None,
    company: str | None,
    title: str | None,
    area: str | None,
) -> str:
    """Build canonical key v1 using ID, URL, then field fingerprint priority."""

    normalized_source = normalize_source_name(source)
    external_id = normalize_external_id(source_job_id)

    if external_id:
        encoded_id = quote(external_id, safe="-._~")
        return f"{CANONICAL_KEY_VERSION}:{normalized_source}:id:{encoded_id}"

    if normalized_source_url:
        return (
            f"{CANONICAL_KEY_VERSION}:{normalized_source}:url:"
            f"{_digest(normalized_source_url)}"
        )

    fingerprint_parts = [
        _normalize_fingerprint_text(company),
        _normalize_fingerprint_text(title),
        _normalize_fingerprint_text(area),
    ]
    if not fingerprint_parts[0] or not fingerprint_parts[1]:
        raise CanonicalIdentityError(
            "company and title are required for canonical fingerprint fallback"
        )

    fingerprint = "\x1f".join(fingerprint_parts)
    return (
        f"{CANONICAL_KEY_VERSION}:{normalized_source}:fingerprint:"
        f"{_digest(fingerprint)}"
    )

"""Stable identity and timing rules for Requirement acceptance execution leases."""
from __future__ import annotations

import json
from hashlib import sha256

DEFAULT_REQUIREMENT_ACCEPTANCE_EXECUTION_LEASE_TTL_SECONDS = 30 * 60


def requirement_acceptance_execution_lease_key(
    *,
    dataset_fingerprint: str,
    title: str,
    reviewer: str,
    provider: str,
    model: str,
    extractor_version: str,
    prompt_version: str,
) -> str:
    """Return the stable lock identity for one resumable acceptance execution."""

    payload = {
        "datasetFingerprint": dataset_fingerprint,
        "title": title,
        "reviewer": reviewer,
        "provider": provider.strip().casefold(),
        "model": model,
        "extractorVersion": extractor_version,
        "promptVersion": prompt_version,
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()

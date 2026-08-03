"""Shared ORM helpers for identifiers and UTC timestamps."""
from datetime import datetime, timezone
from uuid import uuid4


def utc_now() -> datetime:
    """Return an aware UTC timestamp for ORM defaults."""

    return datetime.now(timezone.utc)


def new_prefixed_id(prefix: str) -> str:
    """Create an opaque, readable resource identifier.

    The prefix is for humans and logs only. Callers must not parse business
    meaning from the identifier.
    """

    return f"{prefix}_{uuid4().hex}"


def new_job_id() -> str:
    return new_prefixed_id("job")


def new_job_source_id() -> str:
    return new_prefixed_id("src")


def new_job_import_id() -> str:
    return new_prefixed_id("imp")


def new_job_import_item_id() -> str:
    return new_prefixed_id("itm")


def new_job_import_candidate_id() -> str:
    return new_prefixed_id("cand")


def new_profile_id() -> str:
    return new_prefixed_id("prof")


def new_evidence_id() -> str:
    return new_prefixed_id("ev")


def new_skill_id() -> str:
    return new_prefixed_id("skill")


def new_search_intent_id() -> str:
    return new_prefixed_id("intent")

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


def new_trace_run_id() -> str:
    return new_prefixed_id("run")


def new_profile_eval_run_id() -> str:
    return new_prefixed_id("eval")


def new_profile_eval_case_result_id() -> str:
    return new_prefixed_id("evalcase")


def new_profile_eval_review_id() -> str:
    return new_prefixed_id("review")


def new_job_requirement_extraction_id() -> str:
    return new_prefixed_id("reqrun")


def new_job_requirement_id() -> str:
    return new_prefixed_id("req")


def new_requirement_eval_run_id() -> str:
    return new_prefixed_id("reqeval")


def new_requirement_eval_case_result_id() -> str:
    return new_prefixed_id("reqevalcase")


def new_requirement_eval_review_id() -> str:
    return new_prefixed_id("reqreview")


def new_requirement_review_batch_id() -> str:
    return new_prefixed_id("reqreviewbatch")


def new_requirement_review_batch_case_id() -> str:
    return new_prefixed_id("reqreviewcase")


def new_requirement_review_case_review_id() -> str:
    return new_prefixed_id("reqcasereview")

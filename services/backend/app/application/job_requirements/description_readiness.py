"""Shared prerequisites for analyzing the current job description."""
from __future__ import annotations

from typing import Literal

from app.application.job_queries.models import JobDetail

MIN_DESCRIPTION_CHARS = 40
MAX_DESCRIPTION_CHARS = 50_000

DescriptionLengthBlocker = Literal["description_incomplete", "description_too_long"]


def description_length_blocker(description: str) -> DescriptionLengthBlocker | None:
    characters = len(description.strip())
    if characters < MIN_DESCRIPTION_CHARS:
        return "description_incomplete"
    if characters > MAX_DESCRIPTION_CHARS:
        return "description_too_long"
    return None


def requires_better_capture(job: JobDetail) -> bool:
    eligible = job.requirement_review_eligible
    return eligible is False or (
        eligible is None and (job.source_version or "").startswith(("1.4.", "1.5."))
    )

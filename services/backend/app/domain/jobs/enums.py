"""Stable domain enums for the job data foundation.

These values are shared by persistence, application workflows, and API DTOs.
Keep the string values stable once data has been migrated.
"""
from enum import StrEnum


class RemoteStatus(StrEnum):
    """What the job posting says about remote work."""

    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    UNKNOWN = "unknown"


class RemoteConfidence(StrEnum):
    """Rule confidence for the remote-work classification, not a probability."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ImportOutcome(StrEnum):
    """Result of processing one item in a collector import batch."""

    CREATED = "created"
    UPDATED = "updated"
    SKIPPED = "skipped"
    ERROR = "error"

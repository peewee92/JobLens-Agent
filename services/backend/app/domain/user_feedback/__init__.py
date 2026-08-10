"""UserFeedback domain contract."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class FeedbackDecision(StrEnum):
    INTERESTED = "interested"
    MAYBE = "maybe"
    REJECTED = "rejected"


class FeedbackReason(StrEnum):
    ROLE_FIT = "role_fit"
    SKILL_GAP = "skill_gap"
    COMPENSATION = "compensation"
    LOCATION = "location"
    SENIORITY = "seniority"
    COMPANY = "company"
    WORK_MODE = "work_mode"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class UserFeedbackDraft:
    match_report_id: str
    job_id: str
    decision: FeedbackDecision
    reasons: tuple[FeedbackReason, ...] = ()
    note: str | None = None

    @classmethod
    def create(
        cls,
        *,
        match_report_id: str,
        job_id: str,
        decision: FeedbackDecision,
        reasons: tuple[FeedbackReason, ...] = (),
        note: str | None = None,
    ) -> "UserFeedbackDraft":
        normalized_match_report_id = match_report_id.strip()
        normalized_job_id = job_id.strip()
        normalized_note = note.strip() if note is not None else None
        if normalized_note == "":
            normalized_note = None

        if not normalized_match_report_id:
            raise ValueError("match_report_id must not be blank")
        if not normalized_job_id:
            raise ValueError("job_id must not be blank")

        normalized_reasons = tuple(dict.fromkeys(reasons))
        if decision is FeedbackDecision.REJECTED and not normalized_reasons:
            raise ValueError("rejected feedback requires at least one reason")
        if FeedbackReason.OTHER in normalized_reasons and normalized_note is None:
            raise ValueError("other reason requires a note")

        return cls(
            match_report_id=normalized_match_report_id,
            job_id=normalized_job_id,
            decision=decision,
            reasons=normalized_reasons,
            note=normalized_note,
        )


@dataclass(frozen=True, slots=True)
class StoredUserFeedback:
    id: str
    feedback: UserFeedbackDraft
    created_at: datetime


__all__ = [
    "FeedbackDecision",
    "FeedbackReason",
    "StoredUserFeedback",
    "UserFeedbackDraft",
]

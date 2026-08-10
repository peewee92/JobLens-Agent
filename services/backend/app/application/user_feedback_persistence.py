"""Read-only persistence readiness for UserFeedback."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class UserFeedbackPersistenceReadiness:
    ready: bool
    blocker_codes: tuple[str, ...]
    db_writes: int = 0
    provider_calls: int = 0
    trace_runs_created: int = 0


def check_user_feedback_persistence_readiness(
    *,
    match_reports_ready: bool,
    user_feedback_ready: bool,
) -> UserFeedbackPersistenceReadiness:
    blockers: list[str] = []
    if not match_reports_ready:
        blockers.append("match_report_persistence_not_ready")
    if not user_feedback_ready:
        blockers.append("user_feedback_persistence_not_ready")
    return UserFeedbackPersistenceReadiness(
        ready=not blockers,
        blocker_codes=tuple(blockers),
    )

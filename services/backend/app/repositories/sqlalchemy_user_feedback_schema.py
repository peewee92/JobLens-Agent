"""SQLAlchemy read-only schema inspection for UserFeedback persistence."""
from __future__ import annotations

from sqlalchemy import Engine, inspect

from app.application.user_feedback_persistence import (
    UserFeedbackPersistenceReadiness,
    check_user_feedback_persistence_readiness,
)


def inspect_user_feedback_persistence_readiness(
    engine: Engine,
) -> UserFeedbackPersistenceReadiness:
    inspector = inspect(engine)
    return check_user_feedback_persistence_readiness(
        match_reports_ready=inspector.has_table("match_reports"),
        user_feedback_ready=inspector.has_table("user_feedback"),
    )

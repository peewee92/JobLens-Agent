"""Immutable persisted UserFeedback records."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Index, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.common import new_user_feedback_id, utc_now


class UserFeedbackORM(Base):
    __tablename__ = "user_feedback"
    __table_args__ = (
        Index("ix_user_feedback_match_report_created_at", "match_report_id", "created_at"),
        Index("ix_user_feedback_job_created_at", "job_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(100), primary_key=True, default=new_user_feedback_id)
    match_report_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("match_reports.id", ondelete="RESTRICT"),
        nullable=False,
    )
    job_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("jobs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    reasons: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    note: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=utc_now)

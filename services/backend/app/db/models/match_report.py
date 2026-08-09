"""Immutable persisted MatchReport snapshots."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Index, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.common import new_match_report_id, utc_now


class MatchReportORM(Base):
    __tablename__ = "match_reports"
    __table_args__ = (
        Index("ix_match_reports_job_created_at", "job_id", "created_at"),
        Index("ix_match_reports_trace_run_id", "trace_run_id"),
    )

    id: Mapped[str] = mapped_column(String(100), primary_key=True, default=new_match_report_id)
    job_id: Mapped[str] = mapped_column(String(100), nullable=False)
    profile_id: Mapped[str] = mapped_column(String(100), nullable=False)
    profile_version: Mapped[int] = mapped_column(nullable=False)
    extraction_id: Mapped[str] = mapped_column(String(100), nullable=False)
    eligibility: Mapped[str] = mapped_column(String(20), nullable=False)
    recommendation: Mapped[str] = mapped_column(String(20), nullable=False)
    matcher_version: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    trace_run_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=utc_now)

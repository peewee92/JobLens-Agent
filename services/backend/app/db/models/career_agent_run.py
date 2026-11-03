"""Authoritative runtime state and append-only transitions in the primary DB."""
from datetime import datetime

from sqlalchemy import Float, ForeignKey, Index, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.common import utc_now


class CareerAgentRunORM(Base):
    __tablename__ = "career_agent_runs"
    __table_args__ = (Index("ix_career_agent_runs_updated_at", "updated_at"),)
    thread_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(100), nullable=False)
    request_id: Mapped[str] = mapped_column(String(100), nullable=False)
    lease_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_expires_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    revision: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    current_step: Mapped[str] = mapped_column(String(100), nullable=False)
    analysis_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(default=utc_now, nullable=False)


class CareerAgentRunEventORM(Base):
    __tablename__ = "career_agent_run_events"
    __table_args__ = (UniqueConstraint("thread_id", "revision", name="uq_career_agent_event_revision"),)
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    thread_id: Mapped[str] = mapped_column(ForeignKey("career_agent_runs.thread_id"), nullable=False)
    revision: Mapped[int] = mapped_column(nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=utc_now, nullable=False)

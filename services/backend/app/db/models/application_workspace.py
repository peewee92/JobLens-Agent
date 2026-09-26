"""Persistent Application Workspace snapshots."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Index, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.common import utc_now


class ApplicationWorkspaceORM(Base):
    __tablename__ = "application_workspaces"
    __table_args__ = (
        UniqueConstraint("actor_id", "idempotency_key", name="uq_application_workspace_actor_idempotency"),
        Index("ix_application_workspaces_job_updated", "job_id", "updated_at"),
    )

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    job_id: Mapped[str] = mapped_column(String(100), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(100), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    profile_id: Mapped[str] = mapped_column(String(100), nullable=False)
    profile_version: Mapped[int] = mapped_column(nullable=False)
    search_intent_id: Mapped[str] = mapped_column(String(100), nullable=False)
    search_intent_version: Mapped[int] = mapped_column(nullable=False)
    requirement_extraction_id: Mapped[str] = mapped_column(String(100), nullable=False)
    match_report_id: Mapped[str] = mapped_column(String(100), nullable=False)
    current_fact_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(nullable=False, default=utc_now)


class ResumeVariantORM(Base):
    __tablename__ = "resume_variants"
    __table_args__ = (
        UniqueConstraint("actor_id", "idempotency_key", name="uq_resume_variant_actor_idempotency"),
        Index("ix_resume_variants_workspace_created", "workspace_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("application_workspaces.id", ondelete="CASCADE"), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(100), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    source_profile_id: Mapped[str] = mapped_column(String(100), nullable=False)
    source_profile_version: Mapped[int] = mapped_column(nullable=False)
    requirement_extraction_id: Mapped[str] = mapped_column(String(100), nullable=False)
    highlights: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=utc_now)


class ApplicationTimelineEventORM(Base):
    __tablename__ = "application_timeline_events"
    __table_args__ = (
        UniqueConstraint("actor_id", "idempotency_key", name="uq_application_timeline_actor_idempotency"),
        Index("ix_application_timeline_workspace_created", "workspace_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("application_workspaces.id", ondelete="CASCADE"), nullable=False
    )
    actor_id: Mapped[str] = mapped_column(String(100), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=utc_now)

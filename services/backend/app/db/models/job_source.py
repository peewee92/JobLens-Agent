"""External job-source identity and raw evidence persistence model."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.common import new_job_source_id, utc_now

if TYPE_CHECKING:
    from app.db.models.job import JobORM
    from app.db.models.job_import_item import JobImportItemORM


class JobSourceORM(Base):
    """One external source record linked to a normalized Job."""

    __tablename__ = "job_sources"
    __table_args__ = (
        UniqueConstraint(
            "source",
            "normalized_source_url",
            name="uq_job_sources_source_normalized_url",
        ),
        Index("ix_job_sources_source_source_job_id", "source", "source_job_id"),
        Index("ix_job_sources_job_id", "job_id"),
    )

    id: Mapped[str] = mapped_column(
        String(40), primary_key=True, default=new_job_source_id
    )
    job_id: Mapped[str] = mapped_column(
        String(40),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
    )

    source: Mapped[str] = mapped_column(String(100), nullable=False)
    source_job_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    normalized_source_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    source_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_raw: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    collected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    job: Mapped["JobORM"] = relationship(back_populates="sources")
    import_items: Mapped[list["JobImportItemORM"]] = relationship(
        back_populates="job_source"
    )

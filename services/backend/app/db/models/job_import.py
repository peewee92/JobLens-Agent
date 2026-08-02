"""Collector import-batch persistence model."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import CheckConstraint, DateTime, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.common import new_job_import_id, utc_now

if TYPE_CHECKING:
    from app.db.models.job_import_candidate import JobImportCandidateORM
    from app.db.models.job_import_item import JobImportItemORM


class JobImportORM(Base):
    """Immutable provenance snapshot plus mutable processing counters."""

    __tablename__ = "job_imports"
    __table_args__ = (
        CheckConstraint("received >= 0", name="ck_job_imports_received_non_negative"),
        CheckConstraint("created >= 0", name="ck_job_imports_created_non_negative"),
        CheckConstraint("updated >= 0", name="ck_job_imports_updated_non_negative"),
        CheckConstraint("skipped >= 0", name="ck_job_imports_skipped_non_negative"),
    )

    id: Mapped[str] = mapped_column(
        String(40), primary_key=True, default=new_job_import_id
    )
    source_version: Mapped[str] = mapped_column(String(100), nullable=False)
    collector_version: Mapped[str | None] = mapped_column(String(100), nullable=True)

    received: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    created: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    updated: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    skipped: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")

    errors: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    search_intent_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    source_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    collected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    items: Mapped[list["JobImportItemORM"]] = relationship(
        back_populates="import_batch",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="JobImportItemORM.input_index",
    )
    candidates: Mapped[list["JobImportCandidateORM"]] = relationship(
        back_populates="import_batch",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="JobImportCandidateORM.candidate_index",
    )

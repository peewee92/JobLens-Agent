"""Per-input result row for a collector import batch."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, Enum as SAEnum, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.common import new_job_import_item_id, utc_now
from app.domain.jobs import ImportOutcome

if TYPE_CHECKING:
    from app.db.models.job import JobORM
    from app.db.models.job_import import JobImportORM
    from app.db.models.job_source import JobSourceORM


def _enum_values(enum_cls):
    return [item.value for item in enum_cls]


class JobImportItemORM(Base):
    """How one input item was handled during one import batch."""

    __tablename__ = "job_import_items"
    __table_args__ = (
        UniqueConstraint(
            "import_id",
            "input_index",
            name="uq_job_import_items_import_input_index",
        ),
        CheckConstraint(
            "input_index >= 0",
            name="ck_job_import_items_input_index_non_negative",
        ),
        Index("ix_job_import_items_import_id", "import_id"),
        Index("ix_job_import_items_job_id", "job_id"),
    )

    id: Mapped[str] = mapped_column(
        String(40), primary_key=True, default=new_job_import_item_id
    )
    import_id: Mapped[str] = mapped_column(
        String(40),
        ForeignKey("job_imports.id", ondelete="CASCADE"),
        nullable=False,
    )
    input_index: Mapped[int] = mapped_column(Integer, nullable=False)
    job_id: Mapped[str | None] = mapped_column(
        String(40),
        ForeignKey("jobs.id", ondelete="SET NULL"),
        nullable=True,
    )
    job_source_id: Mapped[str | None] = mapped_column(
        String(40),
        ForeignKey("job_sources.id", ondelete="SET NULL"),
        nullable=True,
    )
    outcome: Mapped[ImportOutcome] = mapped_column(
        SAEnum(
            ImportOutcome,
            values_callable=_enum_values,
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            name="import_outcome_enum",
        ),
        nullable=False,
    )
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    import_batch: Mapped["JobImportORM"] = relationship(back_populates="items")
    job: Mapped["JobORM | None"] = relationship()
    job_source: Mapped["JobSourceORM | None"] = relationship(
        back_populates="import_items"
    )

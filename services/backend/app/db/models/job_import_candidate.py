"""Immutable raw candidate evidence for one Collector import batch."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.common import new_job_import_candidate_id, utc_now

if TYPE_CHECKING:
    from app.db.models.job_import import JobImportORM


class JobImportCandidateORM(Base):
    """One raw entry from ``CollectorReport.candidates``.

    Candidates are immutable import evidence. They are deliberately separate
    from Job and JobSource because rejected or incomplete candidates must not
    enter the stable Job Pool.
    """

    __tablename__ = "job_import_candidates"
    __table_args__ = (
        UniqueConstraint(
            "import_id",
            "candidate_index",
            name="uq_job_import_candidates_import_candidate_index",
        ),
        CheckConstraint(
            "candidate_index >= 0",
            name="ck_job_import_candidates_index_non_negative",
        ),
        Index("ix_job_import_candidates_import_id", "import_id"),
        Index("ix_job_import_candidates_import_keep", "import_id", "keep"),
    )

    id: Mapped[str] = mapped_column(
        String(40), primary_key=True, default=new_job_import_candidate_id
    )
    import_id: Mapped[str] = mapped_column(
        String(40),
        ForeignKey("job_imports.id", ondelete="CASCADE"),
        nullable=False,
    )
    candidate_index: Mapped[int] = mapped_column(Integer, nullable=False)

    keep: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    decision: Mapped[str | None] = mapped_column(String(512), nullable=True)
    pending_detail: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    source_job_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    company: Mapped[str | None] = mapped_column(String(255), nullable=True)

    candidate_raw: Mapped[Any] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    import_batch: Mapped["JobImportORM"] = relationship(back_populates="candidates")

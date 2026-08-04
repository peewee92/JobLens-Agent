"""Persistent operational records for controlled Requirement acceptance runs."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.job import JobORM
    from app.db.models.trace_span import TraceSpanORM
from app.db.models.common import (
    new_requirement_acceptance_canary_review_id,
    new_requirement_acceptance_run_case_id,
    new_requirement_acceptance_run_id,
    utc_now,
)


class RequirementAcceptanceRunORM(Base):
    """One resumable execution for one dataset, reviewer and extraction cohort."""

    __tablename__ = "requirement_acceptance_runs"
    __table_args__ = (
        UniqueConstraint(
            "dataset_fingerprint",
            "title",
            "reviewer",
            "provider",
            "model",
            "extractor_version",
            "prompt_version",
            name="uq_requirement_acceptance_runs_identity",
        ),
        CheckConstraint(
            "total_cases = 20",
            name="ck_requirement_acceptance_runs_formal_sample_size",
        ),
        Index("ix_requirement_acceptance_runs_created_at", "created_at"),
        Index(
            "ix_requirement_acceptance_runs_cohort",
            "provider",
            "model",
            "extractor_version",
            "prompt_version",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(100), primary_key=True, default=new_requirement_acceptance_run_id
    )
    dataset_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    source_version: Mapped[str] = mapped_column(String(32), nullable=False)
    dataset_generated_at: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    reviewer: Mapped[str] = mapped_column(String(160), nullable=False)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    extractor_version: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(100), nullable=False)
    first_import_id: Mapped[str] = mapped_column(
        String(40),
        ForeignKey("job_imports.id", ondelete="RESTRICT"),
        nullable=False,
    )
    last_import_id: Mapped[str] = mapped_column(
        String(40),
        ForeignKey("job_imports.id", ondelete="RESTRICT"),
        nullable=False,
    )
    batch_id: Mapped[str | None] = mapped_column(
        String(90),
        ForeignKey("requirement_review_batches.id", ondelete="RESTRICT"),
        nullable=True,
    )
    total_cases: Mapped[int] = mapped_column(nullable=False, default=20)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    cases: Mapped[list["RequirementAcceptanceRunCaseORM"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="RequirementAcceptanceRunCaseORM.case_index",
    )
    canary_review: Mapped["RequirementAcceptanceCanaryReviewORM | None"] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )


class RequirementAcceptanceRunCaseORM(Base):
    """Mutable operational state for one source Job inside a controlled run."""

    __tablename__ = "requirement_acceptance_run_cases"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "case_index",
            name="uq_requirement_acceptance_run_cases_index",
        ),
        UniqueConstraint(
            "run_id",
            "source_url",
            name="uq_requirement_acceptance_run_cases_source_url",
        ),
        CheckConstraint(
            "case_index >= 0 AND case_index < 20",
            name="ck_requirement_acceptance_run_cases_index",
        ),
        CheckConstraint(
            "status IN ('pending', 'reused', 'extracted', 'failed', 'deferred')",
            name="ck_requirement_acceptance_run_cases_status",
        ),
        CheckConstraint(
            "attempt_count >= 0",
            name="ck_requirement_acceptance_run_cases_attempt_count",
        ),
        Index("ix_requirement_acceptance_run_cases_run_id", "run_id"),
        Index("ix_requirement_acceptance_run_cases_job_id", "job_id"),
        Index("ix_requirement_acceptance_run_cases_status", "status"),
    )

    id: Mapped[str] = mapped_column(
        String(100),
        primary_key=True,
        default=new_requirement_acceptance_run_case_id,
    )
    run_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("requirement_acceptance_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    case_index: Mapped[int] = mapped_column(nullable=False)
    source_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    company: Mapped[str] = mapped_column(String(255), nullable=False)
    description_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    description_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    job_id: Mapped[str] = mapped_column(
        String(40),
        ForeignKey("jobs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    attempt_count: Mapped[int] = mapped_column(nullable=False, default=0)
    extraction_id: Mapped[str | None] = mapped_column(
        String(90),
        ForeignKey("job_requirement_extractions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    trace_run_id: Mapped[str | None] = mapped_column(
        String(80),
        ForeignKey("trace_spans.id", ondelete="RESTRICT"),
        nullable=True,
    )
    error_code: Mapped[str | None] = mapped_column(String(160), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    run: Mapped[RequirementAcceptanceRunORM] = relationship(back_populates="cases")
    job: Mapped["JobORM"] = relationship(
        "JobORM",
        foreign_keys=[job_id],
        lazy="selectin",
    )
    trace: Mapped["TraceSpanORM | None"] = relationship(
        "TraceSpanORM",
        foreign_keys=[trace_run_id],
        lazy="selectin",
    )


class RequirementAcceptanceCanaryReviewORM(Base):
    """One immutable human decision over the attempted Canary evidence of a Run."""

    __tablename__ = "requirement_acceptance_canary_reviews"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            name="uq_requirement_acceptance_canary_reviews_run_id",
        ),
        CheckConstraint(
            "decision IN ('continue', 'stop')",
            name="ck_requirement_acceptance_canary_reviews_decision",
        ),
        Index(
            "ix_requirement_acceptance_canary_reviews_reviewed_at",
            "reviewed_at",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(110),
        primary_key=True,
        default=new_requirement_acceptance_canary_review_id,
    )
    run_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("requirement_acceptance_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    reviewer: Mapped[str] = mapped_column(String(160), nullable=False)
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False)
    reviewed_case_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    reviewed_extraction_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    reviewed_trace_run_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(nullable=False, default=utc_now)

    run: Mapped[RequirementAcceptanceRunORM] = relationship(
        back_populates="canary_review"
    )

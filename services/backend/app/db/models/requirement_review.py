"""Version-frozen manual quality review persistence models."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.common import (
    new_requirement_review_batch_case_id,
    new_requirement_review_batch_id,
    new_requirement_review_case_review_id,
    utc_now,
)


class RequirementReviewBatchORM(Base):
    """One immutable cohort of exact Requirement Extraction versions."""

    __tablename__ = "requirement_review_batches"
    __table_args__ = (
        CheckConstraint(
            "sample_size >= 1 AND sample_size <= 20",
            name="ck_requirement_review_batches_sample_size",
        ),
        Index("ix_requirement_review_batches_created_at", "created_at"),
        Index(
            "ix_requirement_review_batches_cohort",
            "provider",
            "model",
            "extractor_version",
            "prompt_version",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(90), primary_key=True, default=new_requirement_review_batch_id
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    reviewer: Mapped[str] = mapped_column(String(160), nullable=False)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    extractor_version: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(100), nullable=False)
    sample_size: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=utc_now)

    cases: Mapped[list["RequirementReviewBatchCaseORM"]] = relationship(
        back_populates="batch",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="RequirementReviewBatchCaseORM.case_index",
    )


class RequirementReviewBatchCaseORM(Base):
    """One exact JobRequirement Extraction frozen into a review batch."""

    __tablename__ = "requirement_review_batch_cases"
    __table_args__ = (
        ForeignKeyConstraint(
            ["extraction_id", "job_id"],
            ["job_requirement_extractions.id", "job_requirement_extractions.job_id"],
            ondelete="RESTRICT",
            name="fk_requirement_review_cases_extraction_job",
        ),
        UniqueConstraint(
            "batch_id",
            "case_index",
            name="uq_requirement_review_cases_batch_index",
        ),
        UniqueConstraint(
            "batch_id",
            "extraction_id",
            name="uq_requirement_review_cases_batch_extraction",
        ),
        CheckConstraint(
            "case_index >= 0",
            name="ck_requirement_review_cases_index_non_negative",
        ),
        Index("ix_requirement_review_cases_batch_id", "batch_id"),
        Index("ix_requirement_review_cases_job_id", "job_id"),
        Index("ix_requirement_review_cases_extraction_id", "extraction_id"),
    )

    id: Mapped[str] = mapped_column(
        String(100),
        primary_key=True,
        default=new_requirement_review_batch_case_id,
    )
    batch_id: Mapped[str] = mapped_column(
        String(90),
        ForeignKey("requirement_review_batches.id", ondelete="CASCADE"),
        nullable=False,
    )
    case_index: Mapped[int] = mapped_column(nullable=False)
    job_id: Mapped[str] = mapped_column(String(40), nullable=False)
    extraction_id: Mapped[str] = mapped_column(String(90), nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=utc_now)

    batch: Mapped[RequirementReviewBatchORM] = relationship(back_populates="cases")
    review: Mapped["RequirementReviewCaseReviewORM | None"] = relationship(
        back_populates="batch_case",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )


class RequirementReviewCaseReviewORM(Base):
    """One immutable human judgment for a frozen batch case."""

    __tablename__ = "requirement_review_case_reviews"
    __table_args__ = (
        UniqueConstraint(
            "batch_case_id",
            name="uq_requirement_review_case_reviews_case",
        ),
        CheckConstraint(
            "decision IN ('accepted', 'rejected')",
            name="ck_requirement_review_case_reviews_decision",
        ),
        Index(
            "ix_requirement_review_case_reviews_decision_reviewed_at",
            "decision",
            "reviewed_at",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(100),
        primary_key=True,
        default=new_requirement_review_case_review_id,
    )
    batch_case_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("requirement_review_batch_cases.id", ondelete="CASCADE"),
        nullable=False,
    )
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    issue_codes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(nullable=False, default=utc_now)

    batch_case: Mapped[RequirementReviewBatchCaseORM] = relationship(
        back_populates="review"
    )

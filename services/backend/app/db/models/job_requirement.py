"""Immutable Job Requirement Extraction persistence models."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.common import (
    new_job_requirement_extraction_id,
    new_job_requirement_id,
    utc_now,
)
from app.domain.job_requirements import RequirementImportance, RequirementType


class JobRequirementExtractionORM(Base):
    """One immutable extraction of a persisted Job description."""

    __tablename__ = "job_requirement_extractions"
    __table_args__ = (
        UniqueConstraint("id", "job_id", name="uq_job_requirement_extractions_id_job"),
        CheckConstraint(
            "description_characters >= 0",
            name="ck_job_requirement_extractions_description_chars_non_negative",
        ),
        CheckConstraint(
            "requirement_count >= 1",
            name="ck_job_requirement_extractions_count_positive",
        ),
        Index(
            "ix_job_requirement_extractions_job_created",
            "job_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(90),
        primary_key=True,
        default=new_job_requirement_extraction_id,
    )
    job_id: Mapped[str] = mapped_column(
        String(40),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    description_characters: Mapped[int] = mapped_column(nullable=False)
    extractor_version: Mapped[str] = mapped_column(String(100), nullable=False)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(100), nullable=False)
    trace_run_id: Mapped[str] = mapped_column(
        String(80),
        ForeignKey("trace_spans.id", ondelete="RESTRICT"),
        nullable=False,
    )
    requirement_count: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=utc_now)

    requirements: Mapped[list["JobRequirementORM"]] = relationship(
        back_populates="extraction",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="JobRequirementORM.requirement_index",
    )


class JobRequirementORM(Base):
    """One evidence-grounded Requirement produced by an Extraction Run."""

    __tablename__ = "job_requirements"
    __table_args__ = (
        ForeignKeyConstraint(
            ["extraction_id", "job_id"],
            ["job_requirement_extractions.id", "job_requirement_extractions.job_id"],
            ondelete="CASCADE",
            name="fk_job_requirements_extraction_job",
        ),
        UniqueConstraint(
            "extraction_id",
            "requirement_index",
            name="uq_job_requirements_extraction_index",
        ),
        CheckConstraint(
            "requirement_index >= 0",
            name="ck_job_requirements_index_non_negative",
        ),
        CheckConstraint(
            "type IN ('skill', 'experience', 'education', 'responsibility', 'domain', 'constraint')",
            name="ck_job_requirements_type",
        ),
        CheckConstraint(
            "importance IN ('must_have', 'preferred', 'bonus')",
            name="ck_job_requirements_importance",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_job_requirements_confidence_range",
        ),
        Index("ix_job_requirements_job_id", "job_id"),
        Index("ix_job_requirements_capability", "normalized_capability"),
        Index("ix_job_requirements_importance", "importance"),
    )

    id: Mapped[str] = mapped_column(
        String(90),
        primary_key=True,
        default=new_job_requirement_id,
    )
    extraction_id: Mapped[str] = mapped_column(String(90), nullable=False)
    job_id: Mapped[str] = mapped_column(String(40), nullable=False)
    requirement_index: Mapped[int] = mapped_column(nullable=False)
    type: Mapped[RequirementType] = mapped_column(String(20), nullable=False)
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_capability: Mapped[str | None] = mapped_column(String(255), nullable=True)
    importance: Mapped[RequirementImportance] = mapped_column(String(20), nullable=False)
    evidence_span: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    extractor_version: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=utc_now)

    extraction: Mapped[JobRequirementExtractionORM] = relationship(
        back_populates="requirements"
    )

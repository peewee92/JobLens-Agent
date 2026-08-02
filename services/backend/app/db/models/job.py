"""Standardized Job persistence model."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, Enum as SAEnum, Float, Index, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.common import new_job_id, utc_now
from app.domain.jobs import RemoteConfidence, RemoteStatus

if TYPE_CHECKING:
    from app.db.models.job_source import JobSourceORM


def _enum_values(enum_cls):
    return [item.value for item in enum_cls]


class JobORM(Base):
    """JobLens-owned, normalized job entity.

    External platform IDs and raw payloads intentionally live in JobSourceORM.
    """

    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("canonical_key", name="uq_jobs_canonical_key"),
        CheckConstraint(
            "salary_min_k IS NULL OR salary_min_k >= 0",
            name="ck_jobs_salary_min_non_negative",
        ),
        CheckConstraint(
            "salary_max_k IS NULL OR salary_max_k >= 0",
            name="ck_jobs_salary_max_non_negative",
        ),
        CheckConstraint(
            "salary_min_k IS NULL OR salary_max_k IS NULL OR salary_max_k >= salary_min_k",
            name="ck_jobs_salary_range",
        ),
        Index("ix_jobs_area", "area"),
        Index("ix_jobs_salary_min_k", "salary_min_k"),
        Index("ix_jobs_remote_status", "remote_status"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=new_job_id)
    canonical_key: Mapped[str] = mapped_column(String(512), nullable=False)
    canonical_key_version: Mapped[str] = mapped_column(
        String(20), nullable=False, default="v1", server_default="v1"
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    company: Mapped[str] = mapped_column(String(255), nullable=False)
    area: Mapped[str | None] = mapped_column(String(255), nullable=True)
    salary_min_k: Mapped[float | None] = mapped_column(Float, nullable=True)
    salary_max_k: Mapped[float | None] = mapped_column(Float, nullable=True)
    experience: Mapped[str | None] = mapped_column(String(100), nullable=True)
    education: Mapped[str | None] = mapped_column(String(100), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    skills: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    remote_status: Mapped[RemoteStatus] = mapped_column(
        SAEnum(
            RemoteStatus,
            values_callable=_enum_values,
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            name="remote_status_enum",
        ),
        nullable=False,
        default=RemoteStatus.UNKNOWN,
        server_default=RemoteStatus.UNKNOWN.value,
    )
    remote_confidence: Mapped[RemoteConfidence] = mapped_column(
        SAEnum(
            RemoteConfidence,
            values_callable=_enum_values,
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            name="remote_confidence_enum",
        ),
        nullable=False,
        default=RemoteConfidence.LOW,
        server_default=RemoteConfidence.LOW.value,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    sources: Mapped[list["JobSourceORM"]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

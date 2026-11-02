"""Append-only confirmations of one extraction's exact facts."""
from datetime import datetime
from sqlalchemy import DateTime, ForeignKeyConstraint, Index, String
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class JobRequirementConfirmationORM(Base):
    __tablename__ = "job_requirement_confirmations"
    __table_args__ = (
        ForeignKeyConstraint(["extraction_id", "job_id"],
            ["job_requirement_extractions.id", "job_requirement_extractions.job_id"]),
        Index("ix_requirement_confirmation_extraction", "extraction_id"),
    )
    action_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    job_id: Mapped[str] = mapped_column(String(40), nullable=False)
    extraction_id: Mapped[str] = mapped_column(String(90), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    facts_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

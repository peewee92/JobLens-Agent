"""Short-lived single-owner leases for Requirement acceptance execution."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.common import utc_now


class RequirementAcceptanceExecutionLeaseORM(Base):
    """One active execution owner for one stable acceptance-run identity."""

    __tablename__ = "requirement_acceptance_execution_leases"
    __table_args__ = (
        CheckConstraint(
            "expires_at > acquired_at",
            name="ck_requirement_acceptance_execution_leases_expiry",
        ),
        Index(
            "ix_requirement_acceptance_execution_leases_expires_at",
            "expires_at",
        ),
    )

    identity_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    lease_token: Mapped[str] = mapped_column(String(100), nullable=False)
    acquired_at: Mapped[datetime] = mapped_column(nullable=False)
    expires_at: Mapped[datetime] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

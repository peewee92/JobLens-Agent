"""Generic capability trace persistence model."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, Index, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.common import new_trace_run_id, utc_now


class TraceSpanORM(Base):
    """One immutable execution record for an AI or workflow capability."""

    __tablename__ = "trace_spans"
    __table_args__ = (
        CheckConstraint("latency_ms >= 0", name="ck_trace_spans_latency_non_negative"),
        CheckConstraint(
            "input_tokens IS NULL OR input_tokens >= 0",
            name="ck_trace_spans_input_tokens_non_negative",
        ),
        CheckConstraint(
            "output_tokens IS NULL OR output_tokens >= 0",
            name="ck_trace_spans_output_tokens_non_negative",
        ),
        Index("ix_trace_spans_capability_created_at", "capability", "created_at"),
    )

    id: Mapped[str] = mapped_column(
        String(80), primary_key=True, default=new_trace_run_id
    )
    capability: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(100), nullable=False)
    input_refs: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    output: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    latency_ms: Mapped[int] = mapped_column(nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, default=utc_now, index=True
    )

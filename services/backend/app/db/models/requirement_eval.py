"""Immutable Job Requirement Extraction evaluation run models."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, Float, ForeignKey, Index, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.common import (
    new_requirement_eval_case_result_id,
    new_requirement_eval_review_id,
    new_requirement_eval_run_id,
    utc_now,
)


class RequirementEvalRunORM(Base):
    """One immutable evaluation of the Requirement Workflow and dataset."""

    __tablename__ = "requirement_eval_runs"
    __table_args__ = (
        CheckConstraint(
            "total_cases >= 0",
            name="ck_requirement_eval_runs_total_non_negative",
        ),
        CheckConstraint(
            "passed_cases >= 0",
            name="ck_requirement_eval_runs_passed_non_negative",
        ),
        CheckConstraint(
            "passed_cases <= total_cases",
            name="ck_requirement_eval_runs_passed_lte_total",
        ),
        CheckConstraint(
            "case_pass_rate >= 0 AND case_pass_rate <= 1",
            name="ck_requirement_eval_runs_case_rate_range",
        ),
        CheckConstraint(
            "workflow_success_rate >= 0 AND workflow_success_rate <= 1",
            name="ck_requirement_eval_runs_workflow_rate_range",
        ),
        CheckConstraint(
            "capability_recall >= 0 AND capability_recall <= 1",
            name="ck_requirement_eval_runs_capability_recall_range",
        ),
        CheckConstraint(
            "importance_accuracy >= 0 AND importance_accuracy <= 1",
            name="ck_requirement_eval_runs_importance_accuracy_range",
        ),
        CheckConstraint(
            "forbidden_capability_rate >= 0 AND forbidden_capability_rate <= 1",
            name="ck_requirement_eval_runs_forbidden_rate_range",
        ),
        CheckConstraint(
            "mode IN ('fixture', 'live')",
            name="ck_requirement_eval_runs_mode",
        ),
        CheckConstraint(
            "release_eligible = 0 OR (mode = 'live' AND gate_passed = 1)",
            name="ck_requirement_eval_runs_release_eligibility",
        ),
        Index("ix_requirement_eval_runs_created_at", "created_at"),
        Index(
            "ix_requirement_eval_runs_mode_created_at",
            "mode",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(90), primary_key=True, default=new_requirement_eval_run_id
    )
    dataset_version: Mapped[str] = mapped_column(String(120), nullable=False)
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    extractor_version: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(100), nullable=False)
    gate_version: Mapped[str] = mapped_column(String(100), nullable=False)
    baseline_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("requirement_eval_runs.id", ondelete="SET NULL"), nullable=True
    )
    total_cases: Mapped[int] = mapped_column(nullable=False)
    passed_cases: Mapped[int] = mapped_column(nullable=False)
    case_pass_rate: Mapped[float] = mapped_column(Float, nullable=False)
    workflow_success_rate: Mapped[float] = mapped_column(Float, nullable=False)
    capability_recall: Mapped[float] = mapped_column(Float, nullable=False)
    importance_accuracy: Mapped[float] = mapped_column(Float, nullable=False)
    forbidden_capability_rate: Mapped[float] = mapped_column(Float, nullable=False)
    gate_passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    release_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=utc_now)

    cases: Mapped[list["RequirementEvalCaseResultORM"]] = relationship(
        back_populates="eval_run",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="RequirementEvalCaseResultORM.case_id",
    )
    review: Mapped["RequirementEvalReviewORM | None"] = relationship(
        back_populates="eval_run",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )


class RequirementEvalCaseResultORM(Base):
    """One immutable dataset case result linked to its Workflow Trace."""

    __tablename__ = "requirement_eval_case_results"
    __table_args__ = (
        UniqueConstraint(
            "eval_run_id",
            "case_id",
            name="uq_requirement_eval_case_run_case",
        ),
        Index("ix_requirement_eval_case_results_run_id", "eval_run_id"),
        Index(
            "ix_requirement_eval_case_results_trace_run_id",
            "trace_run_id",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(100),
        primary_key=True,
        default=new_requirement_eval_case_result_id,
    )
    eval_run_id: Mapped[str] = mapped_column(
        ForeignKey("requirement_eval_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    case_id: Mapped[str] = mapped_column(String(120), nullable=False)
    trace_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("trace_spans.id", ondelete="SET NULL"), nullable=True
    )
    workflow_succeeded: Mapped[bool] = mapped_column(Boolean, nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    missing_requirements: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    wrong_importance: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    observed_forbidden_capabilities: Mapped[list[str]] = mapped_column(
        JSON, nullable=False
    )
    actual_requirements: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=utc_now)

    eval_run: Mapped[RequirementEvalRunORM] = relationship(back_populates="cases")


class RequirementEvalReviewORM(Base):
    """One immutable human governance decision for a live Requirement Eval Run."""

    __tablename__ = "requirement_eval_reviews"
    __table_args__ = (
        UniqueConstraint(
            "eval_run_id",
            name="uq_requirement_eval_reviews_eval_run_id",
        ),
        CheckConstraint(
            "decision IN ('accepted', 'rejected')",
            name="ck_requirement_eval_reviews_decision",
        ),
        Index(
            "ix_requirement_eval_reviews_decision_reviewed_at",
            "decision",
            "reviewed_at",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(100),
        primary_key=True,
        default=new_requirement_eval_review_id,
    )
    eval_run_id: Mapped[str] = mapped_column(
        ForeignKey("requirement_eval_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    reviewer: Mapped[str] = mapped_column(String(160), nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(nullable=False, default=utc_now)

    eval_run: Mapped[RequirementEvalRunORM] = relationship(back_populates="review")

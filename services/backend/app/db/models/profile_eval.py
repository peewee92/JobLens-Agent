"""Immutable Profile Extraction evaluation run models."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, Float, ForeignKey, Index, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.common import (
    new_profile_eval_case_result_id,
    new_profile_eval_review_id,
    new_profile_eval_run_id,
    utc_now,
)


class ProfileEvalRunORM(Base):
    """One immutable evaluation of a dataset against a configured workflow."""

    __tablename__ = "profile_eval_runs"
    __table_args__ = (
        CheckConstraint("total_cases >= 0", name="ck_profile_eval_runs_total_non_negative"),
        CheckConstraint("passed_cases >= 0", name="ck_profile_eval_runs_passed_non_negative"),
        CheckConstraint("passed_cases <= total_cases", name="ck_profile_eval_runs_passed_lte_total"),
        CheckConstraint("case_pass_rate >= 0 AND case_pass_rate <= 1", name="ck_profile_eval_runs_case_rate_range"),
        CheckConstraint("workflow_success_rate >= 0 AND workflow_success_rate <= 1", name="ck_profile_eval_runs_workflow_rate_range"),
        CheckConstraint("skill_recall >= 0 AND skill_recall <= 1", name="ck_profile_eval_runs_skill_recall_range"),
        CheckConstraint("years_accuracy IS NULL OR (years_accuracy >= 0 AND years_accuracy <= 1)", name="ck_profile_eval_runs_years_accuracy_range"),
        CheckConstraint("forbidden_fact_rate >= 0 AND forbidden_fact_rate <= 1", name="ck_profile_eval_runs_forbidden_rate_range"),
        CheckConstraint("mode IN ('fixture', 'live')", name="ck_profile_eval_runs_mode"),
        CheckConstraint(
            "release_eligible = 0 OR (mode = 'live' AND gate_passed = 1)",
            name="ck_profile_eval_runs_release_eligibility",
        ),
        Index("ix_profile_eval_runs_created_at", "created_at"),
        Index("ix_profile_eval_runs_mode_created_at", "mode", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=new_profile_eval_run_id)
    dataset_version: Mapped[str] = mapped_column(String(120), nullable=False)
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    extractor_version: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(100), nullable=False)
    gate_version: Mapped[str] = mapped_column(String(100), nullable=False)
    baseline_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("profile_eval_runs.id", ondelete="SET NULL"), nullable=True
    )
    total_cases: Mapped[int] = mapped_column(nullable=False)
    passed_cases: Mapped[int] = mapped_column(nullable=False)
    case_pass_rate: Mapped[float] = mapped_column(Float, nullable=False)
    workflow_success_rate: Mapped[float] = mapped_column(Float, nullable=False)
    skill_recall: Mapped[float] = mapped_column(Float, nullable=False)
    years_accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)
    forbidden_fact_rate: Mapped[float] = mapped_column(Float, nullable=False)
    gate_passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    release_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=utc_now)

    cases: Mapped[list["ProfileEvalCaseResultORM"]] = relationship(
        back_populates="eval_run",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ProfileEvalCaseResultORM.case_id",
    )
    review: Mapped["ProfileEvalReviewORM | None"] = relationship(
        back_populates="eval_run",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )


class ProfileEvalCaseResultORM(Base):
    """One immutable dataset-case result linked to the Workflow Trace."""

    __tablename__ = "profile_eval_case_results"
    __table_args__ = (
        UniqueConstraint("eval_run_id", "case_id", name="uq_profile_eval_case_run_case"),
        Index("ix_profile_eval_case_results_run_id", "eval_run_id"),
        Index("ix_profile_eval_case_results_trace_run_id", "trace_run_id"),
    )

    id: Mapped[str] = mapped_column(
        String(90), primary_key=True, default=new_profile_eval_case_result_id
    )
    eval_run_id: Mapped[str] = mapped_column(
        ForeignKey("profile_eval_runs.id", ondelete="CASCADE"), nullable=False
    )
    case_id: Mapped[str] = mapped_column(String(120), nullable=False)
    trace_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("trace_spans.id", ondelete="SET NULL"), nullable=True
    )
    workflow_succeeded: Mapped[bool] = mapped_column(Boolean, nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    failure_codes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    failure_reasons: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    expected_skills: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    actual_skills: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    missing_skills: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    expected_years: Mapped[float | None] = mapped_column(Float, nullable=True)
    actual_years: Mapped[float | None] = mapped_column(Float, nullable=True)
    forbidden_terms: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    observed_forbidden_terms: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    diagnostics: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=utc_now)

    eval_run: Mapped[ProfileEvalRunORM] = relationship(back_populates="cases")


class ProfileEvalReviewORM(Base):
    """One immutable human governance decision for a live Eval Run."""

    __tablename__ = "profile_eval_reviews"
    __table_args__ = (
        UniqueConstraint("eval_run_id", name="uq_profile_eval_reviews_eval_run_id"),
        CheckConstraint(
            "decision IN ('accepted', 'rejected')",
            name="ck_profile_eval_reviews_decision",
        ),
        Index(
            "ix_profile_eval_reviews_decision_reviewed_at",
            "decision",
            "reviewed_at",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(90), primary_key=True, default=new_profile_eval_review_id
    )
    eval_run_id: Mapped[str] = mapped_column(
        ForeignKey("profile_eval_runs.id", ondelete="CASCADE"), nullable=False
    )
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    reviewer: Mapped[str] = mapped_column(String(160), nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(nullable=False, default=utc_now)

    eval_run: Mapped[ProfileEvalRunORM] = relationship(back_populates="review")

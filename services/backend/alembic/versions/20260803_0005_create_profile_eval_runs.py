"""create profile evaluation runs

Revision ID: 20260803_0005
Revises: 20260803_0004
Create Date: 2026-08-03
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260803_0005"
down_revision: str | None = "20260803_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "profile_eval_runs",
        sa.Column("id", sa.String(length=80), nullable=False),
        sa.Column("dataset_version", sa.String(length=120), nullable=False),
        sa.Column("mode", sa.String(length=20), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=False),
        sa.Column("extractor_version", sa.String(length=100), nullable=False),
        sa.Column("prompt_version", sa.String(length=100), nullable=False),
        sa.Column("gate_version", sa.String(length=100), nullable=False),
        sa.Column("baseline_run_id", sa.String(length=80), nullable=True),
        sa.Column("total_cases", sa.Integer(), nullable=False),
        sa.Column("passed_cases", sa.Integer(), nullable=False),
        sa.Column("case_pass_rate", sa.Float(), nullable=False),
        sa.Column("workflow_success_rate", sa.Float(), nullable=False),
        sa.Column("skill_recall", sa.Float(), nullable=False),
        sa.Column("years_accuracy", sa.Float(), nullable=True),
        sa.Column("forbidden_fact_rate", sa.Float(), nullable=False),
        sa.Column("gate_passed", sa.Boolean(), nullable=False),
        sa.Column("release_eligible", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("total_cases >= 0", name="ck_profile_eval_runs_total_non_negative"),
        sa.CheckConstraint("passed_cases >= 0", name="ck_profile_eval_runs_passed_non_negative"),
        sa.CheckConstraint("passed_cases <= total_cases", name="ck_profile_eval_runs_passed_lte_total"),
        sa.CheckConstraint("case_pass_rate >= 0 AND case_pass_rate <= 1", name="ck_profile_eval_runs_case_rate_range"),
        sa.CheckConstraint("workflow_success_rate >= 0 AND workflow_success_rate <= 1", name="ck_profile_eval_runs_workflow_rate_range"),
        sa.CheckConstraint("skill_recall >= 0 AND skill_recall <= 1", name="ck_profile_eval_runs_skill_recall_range"),
        sa.CheckConstraint("years_accuracy IS NULL OR (years_accuracy >= 0 AND years_accuracy <= 1)", name="ck_profile_eval_runs_years_accuracy_range"),
        sa.CheckConstraint("forbidden_fact_rate >= 0 AND forbidden_fact_rate <= 1", name="ck_profile_eval_runs_forbidden_rate_range"),
        sa.CheckConstraint("mode IN ('fixture', 'live')", name="ck_profile_eval_runs_mode"),
        sa.CheckConstraint(
            "release_eligible = 0 OR (mode = 'live' AND gate_passed = 1)",
            name="ck_profile_eval_runs_release_eligibility",
        ),
        sa.ForeignKeyConstraint(["baseline_run_id"], ["profile_eval_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_profile_eval_runs_created_at", "profile_eval_runs", ["created_at"], unique=False)
    op.create_index("ix_profile_eval_runs_mode_created_at", "profile_eval_runs", ["mode", "created_at"], unique=False)

    op.create_table(
        "profile_eval_case_results",
        sa.Column("id", sa.String(length=90), nullable=False),
        sa.Column("eval_run_id", sa.String(length=80), nullable=False),
        sa.Column("case_id", sa.String(length=120), nullable=False),
        sa.Column("trace_run_id", sa.String(length=80), nullable=True),
        sa.Column("workflow_succeeded", sa.Boolean(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("failure_codes", sa.JSON(), nullable=False),
        sa.Column("failure_reasons", sa.JSON(), nullable=False),
        sa.Column("expected_skills", sa.JSON(), nullable=False),
        sa.Column("actual_skills", sa.JSON(), nullable=False),
        sa.Column("missing_skills", sa.JSON(), nullable=False),
        sa.Column("expected_years", sa.Float(), nullable=True),
        sa.Column("actual_years", sa.Float(), nullable=True),
        sa.Column("forbidden_terms", sa.JSON(), nullable=False),
        sa.Column("observed_forbidden_terms", sa.JSON(), nullable=False),
        sa.Column("diagnostics", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["eval_run_id"], ["profile_eval_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["trace_run_id"], ["trace_spans.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("eval_run_id", "case_id", name="uq_profile_eval_case_run_case"),
    )
    op.create_index("ix_profile_eval_case_results_run_id", "profile_eval_case_results", ["eval_run_id"], unique=False)
    op.create_index("ix_profile_eval_case_results_trace_run_id", "profile_eval_case_results", ["trace_run_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_profile_eval_case_results_trace_run_id", table_name="profile_eval_case_results")
    op.drop_index("ix_profile_eval_case_results_run_id", table_name="profile_eval_case_results")
    op.drop_table("profile_eval_case_results")
    op.drop_index("ix_profile_eval_runs_mode_created_at", table_name="profile_eval_runs")
    op.drop_index("ix_profile_eval_runs_created_at", table_name="profile_eval_runs")
    op.drop_table("profile_eval_runs")

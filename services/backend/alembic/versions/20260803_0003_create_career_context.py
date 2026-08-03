"""create versioned career context

Revision ID: 20260803_0003
Revises: 20260802_0002
Create Date: 2026-08-03
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260803_0003"
down_revision: str | None = "20260802_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


evidence_type_enum = sa.Enum(
    "work",
    "project",
    "education",
    "achievement",
    "self_report",
    name="evidence_type_enum",
    native_enum=False,
    create_constraint=True,
)
skill_level_enum = sa.Enum(
    "strong",
    "working",
    "basic",
    "unknown",
    name="skill_level_enum",
    native_enum=False,
    create_constraint=True,
)
seniority_enum = sa.Enum(
    "intern",
    "junior",
    "mid",
    "senior",
    "staff",
    "lead",
    "principal",
    name="seniority_enum",
    native_enum=False,
    create_constraint=True,
)


def upgrade() -> None:
    op.create_table(
        "user_profiles",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column(
            "profile_key",
            sa.String(length=100),
            server_default="default",
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("headline", sa.String(length=500), nullable=False),
        sa.Column("years_of_experience", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "version >= 1", name="ck_user_profiles_version_positive"
        ),
        sa.CheckConstraint(
            "years_of_experience IS NULL OR years_of_experience >= 0",
            name="ck_user_profiles_years_non_negative",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "profile_key", "version", name="uq_user_profiles_key_version"
        ),
    )
    op.create_index(
        "ix_user_profiles_key_version",
        "user_profiles",
        ["profile_key", "version"],
        unique=False,
    )

    op.create_table(
        "search_intents",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column(
            "intent_key",
            sa.String(length=100),
            server_default="default",
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("target_roles", sa.JSON(), nullable=False),
        sa.Column("cities", sa.JSON(), nullable=False),
        sa.Column("remote_accepted", sa.Boolean(), nullable=True),
        sa.Column("minimum_salary_k", sa.Float(), nullable=True),
        sa.Column("seniority", seniority_enum, nullable=True),
        sa.Column("employment_types", sa.JSON(), nullable=False),
        sa.Column("exclude_keywords", sa.JSON(), nullable=False),
        sa.Column("hard_constraints", sa.JSON(), nullable=False),
        sa.Column("soft_preferences", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "version >= 1", name="ck_search_intents_version_positive"
        ),
        sa.CheckConstraint(
            "minimum_salary_k IS NULL OR minimum_salary_k >= 0",
            name="ck_search_intents_salary_non_negative",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "intent_key", "version", name="uq_search_intents_key_version"
        ),
    )
    op.create_index(
        "ix_search_intents_key_version",
        "search_intents",
        ["intent_key", "version"],
        unique=False,
    )

    op.create_table(
        "profile_evidence",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("profile_id", sa.String(length=40), nullable=False),
        sa.Column("evidence_key", sa.String(length=150), nullable=False),
        sa.Column("type", evidence_type_enum, nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["profile_id"], ["user_profiles.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "profile_id", "evidence_key", name="uq_profile_evidence_profile_key"
        ),
    )
    op.create_index(
        "ix_profile_evidence_profile_id",
        "profile_evidence",
        ["profile_id"],
        unique=False,
    )

    op.create_table(
        "profile_skills",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("profile_id", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("normalized_name", sa.String(length=200), nullable=False),
        sa.Column("level", skill_level_enum, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["profile_id"], ["user_profiles.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "profile_id", "normalized_name", name="uq_profile_skills_profile_name"
        ),
    )
    op.create_index(
        "ix_profile_skills_profile_id",
        "profile_skills",
        ["profile_id"],
        unique=False,
    )

    op.create_table(
        "profile_skill_evidence",
        sa.Column("skill_id", sa.String(length=40), nullable=False),
        sa.Column("evidence_id", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(
            ["skill_id"], ["profile_skills.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["evidence_id"], ["profile_evidence.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("skill_id", "evidence_id"),
    )


def downgrade() -> None:
    op.drop_table("profile_skill_evidence")
    op.drop_index("ix_profile_skills_profile_id", table_name="profile_skills")
    op.drop_table("profile_skills")
    op.drop_index("ix_profile_evidence_profile_id", table_name="profile_evidence")
    op.drop_table("profile_evidence")
    op.drop_index("ix_search_intents_key_version", table_name="search_intents")
    op.drop_table("search_intents")
    op.drop_index("ix_user_profiles_key_version", table_name="user_profiles")
    op.drop_table("user_profiles")

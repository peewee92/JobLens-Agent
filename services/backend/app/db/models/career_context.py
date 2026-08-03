"""Versioned career Profile, Evidence, Skill and SearchIntent models."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.common import (
    new_evidence_id,
    new_profile_id,
    new_search_intent_id,
    new_skill_id,
    utc_now,
)
from app.domain.career_context import EvidenceType, Seniority, SkillLevel


def _enum_values(enum_cls: type) -> list[str]:
    return [item.value for item in enum_cls]


class UserProfileORM(Base):
    """One immutable confirmed version in the local Profile stream."""

    __tablename__ = "user_profiles"
    __table_args__ = (
        UniqueConstraint(
            "profile_key", "version", name="uq_user_profiles_key_version"
        ),
        CheckConstraint("version >= 1", name="ck_user_profiles_version_positive"),
        CheckConstraint(
            "years_of_experience IS NULL OR years_of_experience >= 0",
            name="ck_user_profiles_years_non_negative",
        ),
        Index("ix_user_profiles_key_version", "profile_key", "version"),
    )

    id: Mapped[str] = mapped_column(
        String(40), primary_key=True, default=new_profile_id
    )
    profile_key: Mapped[str] = mapped_column(
        String(100), nullable=False, default="default", server_default="default"
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    headline: Mapped[str] = mapped_column(String(500), nullable=False)
    years_of_experience: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    evidence: Mapped[list["ProfileEvidenceORM"]] = relationship(
        back_populates="profile",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ProfileEvidenceORM.id",
    )
    skills: Mapped[list["ProfileSkillORM"]] = relationship(
        back_populates="profile",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ProfileSkillORM.id",
    )


class ProfileEvidenceORM(Base):
    """One confirmed fact supporting capabilities in one Profile version."""

    __tablename__ = "profile_evidence"
    __table_args__ = (
        UniqueConstraint(
            "profile_id", "evidence_key", name="uq_profile_evidence_profile_key"
        ),
        Index("ix_profile_evidence_profile_id", "profile_id"),
    )

    id: Mapped[str] = mapped_column(
        String(40), primary_key=True, default=new_evidence_id
    )
    profile_id: Mapped[str] = mapped_column(
        String(40),
        ForeignKey("user_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    evidence_key: Mapped[str] = mapped_column(String(150), nullable=False)
    type: Mapped[EvidenceType] = mapped_column(
        SAEnum(
            EvidenceType,
            values_callable=_enum_values,
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            name="evidence_type_enum",
        ),
        nullable=False,
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    profile: Mapped[UserProfileORM] = relationship(back_populates="evidence")
    skill_links: Mapped[list["ProfileSkillEvidenceORM"]] = relationship(
        back_populates="evidence",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class ProfileSkillORM(Base):
    """A capability assertion inside one immutable Profile version."""

    __tablename__ = "profile_skills"
    __table_args__ = (
        UniqueConstraint(
            "profile_id", "normalized_name", name="uq_profile_skills_profile_name"
        ),
        Index("ix_profile_skills_profile_id", "profile_id"),
    )

    id: Mapped[str] = mapped_column(
        String(40), primary_key=True, default=new_skill_id
    )
    profile_id: Mapped[str] = mapped_column(
        String(40),
        ForeignKey("user_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(200), nullable=False)
    level: Mapped[SkillLevel] = mapped_column(
        SAEnum(
            SkillLevel,
            values_callable=_enum_values,
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            name="skill_level_enum",
        ),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    profile: Mapped[UserProfileORM] = relationship(back_populates="skills")
    evidence_links: Mapped[list["ProfileSkillEvidenceORM"]] = relationship(
        back_populates="skill",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class ProfileSkillEvidenceORM(Base):
    """Relational link proving which Evidence supports one skill."""

    __tablename__ = "profile_skill_evidence"

    skill_id: Mapped[str] = mapped_column(
        String(40),
        ForeignKey("profile_skills.id", ondelete="CASCADE"),
        primary_key=True,
    )
    evidence_id: Mapped[str] = mapped_column(
        String(40),
        ForeignKey("profile_evidence.id", ondelete="CASCADE"),
        primary_key=True,
    )

    skill: Mapped[ProfileSkillORM] = relationship(back_populates="evidence_links")
    evidence: Mapped[ProfileEvidenceORM] = relationship(back_populates="skill_links")


class SearchIntentORM(Base):
    """One immutable confirmed version in the local SearchIntent stream."""

    __tablename__ = "search_intents"
    __table_args__ = (
        UniqueConstraint(
            "intent_key", "version", name="uq_search_intents_key_version"
        ),
        CheckConstraint("version >= 1", name="ck_search_intents_version_positive"),
        CheckConstraint(
            "minimum_salary_k IS NULL OR minimum_salary_k >= 0",
            name="ck_search_intents_salary_non_negative",
        ),
        Index("ix_search_intents_key_version", "intent_key", "version"),
    )

    id: Mapped[str] = mapped_column(
        String(40), primary_key=True, default=new_search_intent_id
    )
    intent_key: Mapped[str] = mapped_column(
        String(100), nullable=False, default="default", server_default="default"
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    target_roles: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    cities: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    remote_accepted: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    minimum_salary_k: Mapped[float | None] = mapped_column(Float, nullable=True)
    seniority: Mapped[Seniority | None] = mapped_column(
        SAEnum(
            Seniority,
            values_callable=_enum_values,
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            name="seniority_enum",
        ),
        nullable=True,
    )
    employment_types: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    exclude_keywords: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    hard_constraints: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    soft_preferences: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

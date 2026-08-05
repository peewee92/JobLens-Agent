"""SQLAlchemy persistence and read adapters for career context."""
from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.application.career_context.models import (
    CareerContextSnapshot,
    EvidenceDetail,
    ProfileDetail,
    SaveProfileCommand,
    SaveSearchIntentCommand,
    SearchIntentDetail,
    SkillDetail,
)
from app.application.ports.career_context_repository import (
    AbstractCareerContextQueryRepository,
    AbstractCareerContextRepository,
)
from app.db.models import (
    ProfileEvidenceORM,
    ProfileSkillEvidenceORM,
    ProfileSkillORM,
    SearchIntentORM,
    UserProfileORM,
)

SessionFactory = Callable[[], Session]
PROFILE_KEY = "default"
SEARCH_INTENT_KEY = "default"


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _profile_detail_from_rows(
    profile: UserProfileORM,
    evidence_rows: list[ProfileEvidenceORM],
    skill_rows: list[ProfileSkillORM],
    link_rows: list[tuple[str, str]],
) -> ProfileDetail:
    evidence_by_id = {item.id: item for item in evidence_rows}
    evidence_ids_by_skill: dict[str, list[str]] = {}
    for skill_id, evidence_id in link_rows:
        if evidence_id in evidence_by_id:
            evidence_ids_by_skill.setdefault(skill_id, []).append(evidence_id)

    return ProfileDetail(
        id=profile.id,
        version=profile.version,
        headline=profile.headline,
        years_of_experience=profile.years_of_experience,
        evidence=tuple(
            EvidenceDetail(
                id=item.id,
                key=item.evidence_key,
                type=item.type,
                summary=item.summary,
                source=item.source,
            )
            for item in evidence_rows
        ),
        skills=tuple(
            SkillDetail(
                id=item.id,
                name=item.name,
                level=item.level,
                evidence_ids=tuple(evidence_ids_by_skill.get(item.id, ())),
            )
            for item in skill_rows
        ),
        created_at=_as_utc(profile.created_at),
    )


def _load_profile(session: Session, profile_id: str) -> ProfileDetail | None:
    profile = session.get(UserProfileORM, profile_id)
    if profile is None:
        return None
    evidence_rows = list(
        session.scalars(
            select(ProfileEvidenceORM)
            .where(ProfileEvidenceORM.profile_id == profile_id)
            .order_by(ProfileEvidenceORM.evidence_key.asc())
        )
    )
    skill_rows = list(
        session.scalars(
            select(ProfileSkillORM)
            .where(ProfileSkillORM.profile_id == profile_id)
            .order_by(ProfileSkillORM.normalized_name.asc())
        )
    )
    skill_ids = [item.id for item in skill_rows]
    link_rows: list[tuple[str, str]] = []
    if skill_ids:
        link_rows = [
            (row.skill_id, row.evidence_id)
            for row in session.execute(
                select(
                    ProfileSkillEvidenceORM.skill_id,
                    ProfileSkillEvidenceORM.evidence_id,
                )
                .where(ProfileSkillEvidenceORM.skill_id.in_(skill_ids))
                .order_by(
                    ProfileSkillEvidenceORM.skill_id.asc(),
                    ProfileSkillEvidenceORM.evidence_id.asc(),
                )
            )
        ]
    return _profile_detail_from_rows(
        profile, evidence_rows, skill_rows, link_rows
    )


def _search_intent_detail(model: SearchIntentORM) -> SearchIntentDetail:
    return SearchIntentDetail(
        id=model.id,
        version=model.version,
        target_roles=tuple(model.target_roles),
        cities=tuple(model.cities),
        remote_accepted=model.remote_accepted,
        minimum_salary_k=model.minimum_salary_k,
        seniority=model.seniority,
        employment_types=tuple(model.employment_types),
        exclude_keywords=tuple(model.exclude_keywords),
        hard_constraints=tuple(model.hard_constraints),
        soft_preferences=tuple(model.soft_preferences),
        created_at=_as_utc(model.created_at),
    )


class SqlAlchemyCareerContextRepository(AbstractCareerContextRepository):
    """Write-side adapter using a caller-owned Session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def current_profile_version(self) -> int:
        value = self._session.scalar(
            select(func.max(UserProfileORM.version)).where(
                UserProfileORM.profile_key == PROFILE_KEY
            )
        )
        return int(value or 0)

    def add_profile_version(
        self,
        command: SaveProfileCommand,
        *,
        version: int,
    ) -> ProfileDetail:
        profile = UserProfileORM(
            profile_key=PROFILE_KEY,
            version=version,
            headline=command.headline,
            years_of_experience=command.years_of_experience,
        )
        self._session.add(profile)
        self._session.flush()

        evidence_rows = [
            ProfileEvidenceORM(
                profile_id=profile.id,
                evidence_key=item.key,
                type=item.type,
                summary=item.summary,
                source=item.source,
            )
            for item in command.evidence
        ]
        self._session.add_all(evidence_rows)
        self._session.flush()
        evidence_by_key = {
            item.evidence_key.casefold(): item.id for item in evidence_rows
        }

        skill_rows = [
            ProfileSkillORM(
                profile_id=profile.id,
                name=item.name,
                normalized_name=item.name.casefold(),
                level=item.level,
            )
            for item in command.skills
        ]
        self._session.add_all(skill_rows)
        self._session.flush()

        links: list[ProfileSkillEvidenceORM] = []
        link_pairs: list[tuple[str, str]] = []
        for skill_input, skill_row in zip(command.skills, skill_rows, strict=True):
            for key in skill_input.evidence_keys:
                evidence_id = evidence_by_key[key.casefold()]
                links.append(
                    ProfileSkillEvidenceORM(
                        skill_id=skill_row.id,
                        evidence_id=evidence_id,
                    )
                )
                link_pairs.append((skill_row.id, evidence_id))
        self._session.add_all(links)
        self._session.flush()

        return _profile_detail_from_rows(
            profile,
            evidence_rows,
            skill_rows,
            link_pairs,
        )

    def current_search_intent_version(self) -> int:
        value = self._session.scalar(
            select(func.max(SearchIntentORM.version)).where(
                SearchIntentORM.intent_key == SEARCH_INTENT_KEY
            )
        )
        return int(value or 0)

    def add_search_intent_version(
        self,
        command: SaveSearchIntentCommand,
        *,
        version: int,
    ) -> SearchIntentDetail:
        model = SearchIntentORM(
            intent_key=SEARCH_INTENT_KEY,
            version=version,
            target_roles=list(command.target_roles),
            cities=list(command.cities),
            remote_accepted=command.remote_accepted,
            minimum_salary_k=command.minimum_salary_k,
            seniority=command.seniority,
            employment_types=list(command.employment_types),
            exclude_keywords=list(command.exclude_keywords),
            hard_constraints=list(command.hard_constraints),
            soft_preferences=list(command.soft_preferences),
        )
        self._session.add(model)
        self._session.flush()
        return _search_intent_detail(model)


class SqlAlchemyCareerContextQueryRepository(
    AbstractCareerContextQueryRepository
):
    """Read the latest confirmed local-user career context."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def get_current_context(self) -> CareerContextSnapshot:
        """Select both current IDs in one statement, then load those exact versions."""

        with self._session_factory() as session:
            profile_id_query = (
                select(UserProfileORM.id)
                .where(UserProfileORM.profile_key == PROFILE_KEY)
                .order_by(UserProfileORM.version.desc())
                .limit(1)
                .scalar_subquery()
            )
            intent_id_query = (
                select(SearchIntentORM.id)
                .where(SearchIntentORM.intent_key == SEARCH_INTENT_KEY)
                .order_by(SearchIntentORM.version.desc())
                .limit(1)
                .scalar_subquery()
            )
            profile_id, intent_id = session.execute(
                select(profile_id_query, intent_id_query)
            ).one()
            profile = (
                _load_profile(session, profile_id)
                if profile_id is not None
                else None
            )
            intent_model = (
                session.get(SearchIntentORM, intent_id)
                if intent_id is not None
                else None
            )
            return CareerContextSnapshot(
                profile=profile,
                search_intent=(
                    _search_intent_detail(intent_model)
                    if intent_model is not None
                    else None
                ),
            )

    def get_current_profile(self) -> ProfileDetail | None:
        with self._session_factory() as session:
            profile_id = session.scalar(
                select(UserProfileORM.id)
                .where(UserProfileORM.profile_key == PROFILE_KEY)
                .order_by(UserProfileORM.version.desc())
                .limit(1)
            )
            return (
                _load_profile(session, profile_id)
                if profile_id is not None
                else None
            )

    def get_current_search_intent(self) -> SearchIntentDetail | None:
        with self._session_factory() as session:
            model = session.scalar(
                select(SearchIntentORM)
                .where(SearchIntentORM.intent_key == SEARCH_INTENT_KEY)
                .order_by(SearchIntentORM.version.desc())
                .limit(1)
            )
            return None if model is None else _search_intent_detail(model)

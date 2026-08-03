"""Application workflows for confirmed Profile and SearchIntent versions."""
from __future__ import annotations

from collections.abc import Callable, Iterable

from app.application.career_context.errors import (
    ContextVersionConflictError,
    InvalidCareerContextError,
    ProfileNotFoundError,
    SearchIntentNotFoundError,
)
from app.application.career_context.models import (
    EvidenceInput,
    ProfileDetail,
    SaveProfileCommand,
    SaveSearchIntentCommand,
    SearchIntentDetail,
    SkillInput,
)
from app.application.ports.career_context_repository import (
    AbstractCareerContextQueryRepository,
)
from app.application.ports.career_context_unit_of_work import (
    AbstractCareerContextUnitOfWork,
)

CareerContextUnitOfWorkFactory = Callable[[], AbstractCareerContextUnitOfWork]


def _required_text(value: str, field: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise InvalidCareerContextError(f"{field} must not be empty")
    return normalized


def _unique_text(values: Iterable[str], field: str) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.strip()
        if not normalized:
            continue
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    if field == "targetRoles" and not result:
        raise InvalidCareerContextError("targetRoles must contain at least one role")
    return tuple(result)


class SaveProfileUseCase:
    def __init__(self, uow_factory: CareerContextUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, command: SaveProfileCommand) -> ProfileDetail:
        normalized = self._normalize(command)
        with self._uow_factory() as uow:
            current = uow.context.current_profile_version()
            if current != normalized.expected_version:
                raise ContextVersionConflictError(
                    "profile", normalized.expected_version, current
                )
            result = uow.context.add_profile_version(
                normalized,
                version=current + 1,
            )
            uow.commit()
            return result

    @staticmethod
    def _normalize(command: SaveProfileCommand) -> SaveProfileCommand:
        if command.expected_version < 0:
            raise InvalidCareerContextError("expectedVersion must be non-negative")
        if command.years_of_experience is not None and command.years_of_experience < 0:
            raise InvalidCareerContextError(
                "yearsOfExperience must be non-negative"
            )

        evidence: list[EvidenceInput] = []
        evidence_keys: dict[str, str] = {}
        for item in command.evidence:
            key = _required_text(item.key, "evidence.key")
            folded = key.casefold()
            if folded in evidence_keys:
                raise InvalidCareerContextError(
                    f"duplicate evidence key: {key}"
                )
            evidence_keys[folded] = key
            evidence.append(
                EvidenceInput(
                    key=key,
                    type=item.type,
                    summary=_required_text(item.summary, "evidence.summary"),
                    source=_required_text(item.source, "evidence.source"),
                )
            )

        skills: list[SkillInput] = []
        skill_names: set[str] = set()
        for item in command.skills:
            name = _required_text(item.name, "skill.name")
            normalized_name = name.casefold()
            if normalized_name in skill_names:
                raise InvalidCareerContextError(f"duplicate skill name: {name}")
            skill_names.add(normalized_name)

            keys = _unique_text(item.evidence_keys, "evidenceKeys")
            if not keys:
                raise InvalidCareerContextError(
                    f"skill '{name}' must reference at least one evidence key"
                )
            missing = [
                key
                for key in keys
                if key.casefold() not in evidence_keys
            ]
            if missing:
                raise InvalidCareerContextError(
                    f"skill '{name}' references unknown evidence keys: {', '.join(missing)}"
                )
            canonical_keys = tuple(evidence_keys[key.casefold()] for key in keys)
            skills.append(
                SkillInput(
                    name=name,
                    level=item.level,
                    evidence_keys=canonical_keys,
                )
            )

        return SaveProfileCommand(
            expected_version=command.expected_version,
            headline=_required_text(command.headline, "headline"),
            years_of_experience=command.years_of_experience,
            evidence=tuple(evidence),
            skills=tuple(skills),
        )


class GetProfileUseCase:
    def __init__(self, repository: AbstractCareerContextQueryRepository) -> None:
        self._repository = repository

    def execute(self) -> ProfileDetail:
        result = self._repository.get_current_profile()
        if result is None:
            raise ProfileNotFoundError()
        return result


class SaveSearchIntentUseCase:
    def __init__(self, uow_factory: CareerContextUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, command: SaveSearchIntentCommand) -> SearchIntentDetail:
        normalized = self._normalize(command)
        with self._uow_factory() as uow:
            current = uow.context.current_search_intent_version()
            if current != normalized.expected_version:
                raise ContextVersionConflictError(
                    "search_intent", normalized.expected_version, current
                )
            result = uow.context.add_search_intent_version(
                normalized,
                version=current + 1,
            )
            uow.commit()
            return result

    @staticmethod
    def _normalize(command: SaveSearchIntentCommand) -> SaveSearchIntentCommand:
        if command.expected_version < 0:
            raise InvalidCareerContextError("expectedVersion must be non-negative")
        if command.minimum_salary_k is not None and command.minimum_salary_k < 0:
            raise InvalidCareerContextError("minimumSalaryK must be non-negative")

        return SaveSearchIntentCommand(
            expected_version=command.expected_version,
            target_roles=_unique_text(command.target_roles, "targetRoles"),
            cities=_unique_text(command.cities, "cities"),
            remote_accepted=command.remote_accepted,
            minimum_salary_k=command.minimum_salary_k,
            seniority=command.seniority,
            employment_types=_unique_text(
                command.employment_types, "employmentTypes"
            ),
            exclude_keywords=_unique_text(
                command.exclude_keywords, "excludeKeywords"
            ),
            hard_constraints=_unique_text(
                command.hard_constraints, "hardConstraints"
            ),
            soft_preferences=_unique_text(
                command.soft_preferences, "softPreferences"
            ),
        )


class GetSearchIntentUseCase:
    def __init__(self, repository: AbstractCareerContextQueryRepository) -> None:
        self._repository = repository

    def execute(self) -> SearchIntentDetail:
        result = self._repository.get_current_search_intent()
        if result is None:
            raise SearchIntentNotFoundError()
        return result

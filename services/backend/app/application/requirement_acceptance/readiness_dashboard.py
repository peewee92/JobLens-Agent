"""Read-only dashboard orchestration for formal Requirement acceptance."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
import json
from pathlib import Path
from typing import Any

from app.application.ports.requirement_acceptance_run_repository import (
    AbstractRequirementAcceptanceRunQueryRepository,
)
from app.application.requirement_acceptance.errors import (
    InvalidRequirementAcceptanceDatasetError,
)
from app.application.requirement_acceptance.local_bootstrap import (
    private_dataset_path,
)
from app.application.requirement_acceptance.readiness import (
    RequirementAcceptanceReadinessResult,
    evaluate_requirement_acceptance_readiness,
)
from app.application.requirement_acceptance.runtime_environment import (
    read_requirement_acceptance_database_revision,
    requirement_acceptance_migration_head,
)
from app.application.requirement_acceptance.use_case import (
    preflight_requirement_acceptance_dataset,
)

DatabaseRevisionReader = Callable[
    [str, Path],
    tuple[bool, str | None, str | None],
]
MigrationHeadReader = Callable[[Path], str]


class RequirementAcceptanceDatasetState(StrEnum):
    MISSING = "missing"
    SELECTION_REQUIRED = "selection_required"
    INVALID = "invalid"
    READY = "ready"


@dataclass(frozen=True, slots=True)
class RequirementAcceptanceReadinessDashboard:
    dataset_state: RequirementAcceptanceDatasetState
    dataset_candidate_count: int
    dataset_file_name: str | None
    readiness: RequirementAcceptanceReadinessResult


class GetRequirementAcceptanceReadinessDashboardUseCase:
    """Derive the next safe action without Provider calls or database writes."""

    def __init__(
        self,
        *,
        runs: AbstractRequirementAcceptanceRunQueryRepository,
        private_root: Path,
        backend_root: Path,
        database_url: str,
        provider: str,
        model: str,
        api_key_configured: bool,
        extractor_version: str,
        prompt_version: str,
        web_base_url: str,
        database_revision_reader: DatabaseRevisionReader | None = None,
        migration_head_reader: MigrationHeadReader | None = None,
    ) -> None:
        self._runs = runs
        self._private_root = private_root.resolve()
        self._backend_root = backend_root.resolve()
        self._database_url = database_url
        self._provider = provider.strip().casefold() or "disabled"
        self._model = model.strip()
        self._api_key_configured = api_key_configured
        self._extractor_version = extractor_version.strip()
        self._prompt_version = prompt_version.strip()
        self._web_base_url = web_base_url.rstrip("/")
        self._database_revision_reader = (
            database_revision_reader or _default_database_revision_reader
        )
        self._migration_head_reader = (
            migration_head_reader or _default_migration_head_reader
        )

    def execute(
        self,
        *,
        reviewer: str,
        title: str | None,
        max_new_extractions: int | None,
    ) -> RequirementAcceptanceReadinessDashboard:
        candidates = tuple(
            sorted(
                path
                for path in (self._private_root / "datasets").glob("formal-*.json")
                if path.is_file()
            )
        )
        preflight = None
        dataset_state = RequirementAcceptanceDatasetState.MISSING
        dataset_file_name = None
        dataset_blocker_code = "formal_dataset_missing"
        dataset_blocker_message = (
            "No canonical private formal Requirement acceptance dataset is staged. "
            "Use the guarded bootstrap before any live Provider operation."
        )
        payload: dict[str, Any] | None = None

        if len(candidates) > 1:
            dataset_state = RequirementAcceptanceDatasetState.SELECTION_REQUIRED
            dataset_blocker_code = "formal_dataset_selection_required"
            dataset_blocker_message = (
                "Multiple canonical formal datasets are staged. Select and retain exactly "
                "one active dataset before deriving a stable Run identity."
            )
        elif len(candidates) == 1:
            candidate = candidates[0]
            dataset_file_name = candidate.name
            try:
                payload = _load_payload(candidate)
                preflight = preflight_requirement_acceptance_dataset(payload)
                expected = private_dataset_path(
                    private_root=self._private_root,
                    dataset_fingerprint=preflight.dataset_fingerprint,
                ).resolve()
                if candidate.resolve() != expected:
                    raise InvalidRequirementAcceptanceDatasetError(
                        "Formal dataset file name does not match its Dataset Fingerprint."
                    )
            except InvalidRequirementAcceptanceDatasetError as error:
                preflight = None
                dataset_state = RequirementAcceptanceDatasetState.INVALID
                dataset_blocker_code = "formal_dataset_invalid"
                dataset_blocker_message = str(error)
            else:
                dataset_state = RequirementAcceptanceDatasetState.READY
                dataset_blocker_code = None
                dataset_blocker_message = None

        normalized_reviewer = reviewer.strip()
        normalized_title = (title or "").strip()
        if not normalized_title and payload is not None:
            normalized_title = _default_title(payload, dataset_file_name or "formal")

        migration_head = self._migration_head_reader(self._backend_root)
        database_reachable, database_revision, database_error = (
            self._database_revision_reader(
                self._database_url,
                self._backend_root,
            )
        )

        existing_run = None
        if (
            preflight is not None
            and database_reachable
            and database_revision == migration_head
            and normalized_reviewer
            and normalized_title
            and self._provider == "openai"
            and self._model
        ):
            existing_run = self._runs.get_by_identity(
                dataset_fingerprint=preflight.dataset_fingerprint,
                title=normalized_title,
                reviewer=normalized_reviewer,
                provider=self._provider,
                model=self._model,
                extractor_version=self._extractor_version,
                prompt_version=self._prompt_version,
            )

        readiness = evaluate_requirement_acceptance_readiness(
            preflight=preflight,
            provider=self._provider,
            model=self._model,
            api_key_configured=self._api_key_configured,
            reviewer=normalized_reviewer,
            title=normalized_title,
            max_new_extractions=max_new_extractions,
            database_reachable=database_reachable,
            database_revision=database_revision,
            migration_head=migration_head,
            existing_run=existing_run,
            web_base_url=self._web_base_url,
            database_error=database_error,
            dataset_blocker_code=dataset_blocker_code,
            dataset_blocker_message=dataset_blocker_message,
        )
        return RequirementAcceptanceReadinessDashboard(
            dataset_state=dataset_state,
            dataset_candidate_count=len(candidates),
            dataset_file_name=dataset_file_name,
            readiness=readiness,
        )


def _load_payload(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise InvalidRequirementAcceptanceDatasetError(
            f"Formal dataset could not be read as JSON: {type(error).__name__}"
        ) from error
    if not isinstance(payload, dict):
        raise InvalidRequirementAcceptanceDatasetError(
            "Formal dataset root must be a JSON object."
        )
    return payload


def _default_title(payload: dict[str, Any], fallback: str) -> str:
    generated_at = payload.get("generatedAt")
    if isinstance(generated_at, str) and generated_at.strip():
        return f"Requirement acceptance {generated_at.strip()}"
    return f"Requirement acceptance {fallback}"


def _default_database_revision_reader(
    database_url: str,
    backend_root: Path,
) -> tuple[bool, str | None, str | None]:
    return read_requirement_acceptance_database_revision(
        database_url,
        backend_root=backend_root,
    )


def _default_migration_head_reader(backend_root: Path) -> str:
    return requirement_acceptance_migration_head(backend_root=backend_root)

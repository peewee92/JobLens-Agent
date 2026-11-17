"""A user may correct their pasted description, not a collector observation."""
from dataclasses import dataclass
from hashlib import sha256
from typing import Literal, Protocol

from app.application.job_requirements.description_readiness import description_length_blocker


def description_digest(value: str | None) -> str:
    return sha256((value or "").encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ManualDescriptionSaved:
    job_id: str
    description_sha256: str
    changed: bool


ManualDescriptionBlocker = Literal["not_found", "source_read_only", "changed", "identity_conflict", "invalid_description"]


class ManualDescriptionRepository(Protocol):
    def save(self, job_id: str, *, description: str, expected_sha256: str) -> ManualDescriptionSaved | ManualDescriptionBlocker: ...


class ReviseManualJobDescription:
    def __init__(self, repository: ManualDescriptionRepository):
        self._repository = repository

    def execute(self, job_id: str, *, description: str, expected_sha256: str) -> ManualDescriptionSaved | ManualDescriptionBlocker:
        if description_length_blocker(description):
            return "invalid_description"
        return self._repository.save(job_id, description=description, expected_sha256=expected_sha256)

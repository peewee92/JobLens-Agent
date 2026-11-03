"""User-controlled, version-checked job availability command."""
from typing import Protocol


class JobAvailabilityWriter(Protocol):
    def set(self, job_id: str, *, inactive: bool, expected_revision: int): ...


class SetJobAvailabilityUseCase:
    def __init__(self, writer: JobAvailabilityWriter):
        self._writer = writer

    def execute(self, job_id: str, *, inactive: bool, expected_revision: int):
        return self._writer.set(job_id, inactive=inactive, expected_revision=expected_revision)

"""One posting's explicit user confirmation, never a model-quality decision."""
from dataclasses import asdict, dataclass
from datetime import datetime, UTC
from hashlib import sha256
import json
from typing import Callable, Protocol, Self, TYPE_CHECKING

from app.application.job_requirements.models import JobRequirementExtractionDetail

if TYPE_CHECKING:
    from app.application.job_requirements.release import JobRequirementReleaseReadiness


def requirement_facts_digest(extraction: JobRequirementExtractionDetail) -> str:
    facts = {
        "extractionId": extraction.extraction_id, "jobId": extraction.job_id,
        "inputHash": extraction.input_hash, "traceRunId": extraction.trace_run_id,
        "extractorVersion": extraction.extractor_version, "provider": extraction.provider,
        "model": extraction.model, "promptVersion": extraction.prompt_version,
        "semanticPolicyVersion": extraction.semantic_policy_version,
        "requirementCount": extraction.requirement_count,
        "requirements": [asdict(item) for item in extraction.requirements],
    }
    return sha256(json.dumps(facts, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class RequirementConfirmation:
    action_id: str
    job_id: str
    extraction_id: str
    input_hash: str
    facts_digest: str
    confirmed_at: datetime


class RequirementConfirmationConflict(ValueError):
    pass


class RequirementConfirmationUnitOfWork(Protocol):
    def __enter__(self) -> Self: ...
    def __exit__(self, *args) -> None: ...
    def get(self, action_id: str) -> RequirementConfirmation | None: ...
    def inspect(self, job_id: str) -> "JobRequirementReleaseReadiness": ...
    def add(self, record: RequirementConfirmation) -> None: ...
    def commit(self) -> None: ...


class ConfirmJobRequirementsUseCase:
    def __init__(self, uow_factory: Callable[[], RequirementConfirmationUnitOfWork]):
        self._uow_factory = uow_factory

    def execute(self, *, job_id: str, extraction_id: str, input_hash: str,
                facts_digest: str, action_id: str) -> RequirementConfirmation:
        with self._uow_factory() as uow:
            previous = uow.get(action_id)
            if previous is not None:
                if (previous.job_id, previous.extraction_id, previous.input_hash, previous.facts_digest) != (
                    job_id, extraction_id, input_hash, facts_digest,
                ):
                    raise RequirementConfirmationConflict("confirmation_action_conflict")
                return previous
            readiness = uow.inspect(job_id)
            if (not readiness.release_eligible or readiness.extraction_id != extraction_id
                or readiness.extraction_input_hash != input_hash
                or readiness.requirement_facts_digest != facts_digest):
                raise RequirementConfirmationConflict("requirement_confirmation_facts_changed")
            record = RequirementConfirmation(action_id, job_id, extraction_id, input_hash,
                                             facts_digest, datetime.now(UTC))
            uow.add(record)
            uow.commit()
            return record

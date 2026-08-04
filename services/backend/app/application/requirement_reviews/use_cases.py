"""Application policies for Requirement manual quality review batches."""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from hashlib import sha256
import json
from uuid import uuid4

from app.application.ports.requirement_review_repository import (
    AbstractRequirementReviewQueryRepository,
)
from app.application.ports.requirement_review_unit_of_work import (
    AbstractRequirementReviewUnitOfWork,
)
from app.application.requirement_reviews.errors import (
    AcceptedRequirementReviewBaselineNotFoundError,
    InvalidRequirementCaseReviewError,
    InvalidRequirementReviewBatchError,
    InvalidRequirementReviewBatchFinalDecisionError,
    RequirementReviewBatchFinalDecisionAlreadyExistsError,
    RequirementReviewBatchNotFoundError,
    RequirementReviewCaseAlreadyReviewedError,
    RequirementReviewCaseNotFoundError,
)
from app.application.requirement_reviews.models import (
    AcceptedRequirementReviewBaseline,
    RequirementReviewBatchCaseWrite,
    RequirementReviewBatchFinalDecision,
    RequirementReviewBatchFinalDecisionDetail,
    RequirementReviewBatchFinalDecisionWrite,
    RequirementReviewBatchDetail,
    RequirementReviewBatchPage,
    RequirementReviewBatchWrite,
    RequirementReviewCandidatePage,
    RequirementReviewCaseReviewDetail,
    RequirementReviewCaseReviewWrite,
    RequirementReviewDecision,
    RequirementReviewIssueCode,
)

RequirementReviewUnitOfWorkFactory = Callable[[], AbstractRequirementReviewUnitOfWork]
MAX_BATCH_SIZE = 20
MIN_REVIEW_NOTES = 10
MIN_FINAL_DECISION_NOTES = 20
FINAL_DECISION_EVIDENCE_SCHEMA_VERSION = "requirement-review-batch-evidence-v1"


class ListRequirementReviewCandidatesUseCase:
    def __init__(self, repository: AbstractRequirementReviewQueryRepository) -> None:
        self._repository = repository

    def execute(self, *, limit: int, offset: int) -> RequirementReviewCandidatePage:
        return self._repository.list_candidates(limit=limit, offset=offset)


class CreateRequirementReviewBatchUseCase:
    def __init__(
        self,
        repository: AbstractRequirementReviewQueryRepository,
        uow_factory: RequirementReviewUnitOfWorkFactory,
    ) -> None:
        self._repository = repository
        self._uow_factory = uow_factory

    def execute(
        self,
        *,
        title: str,
        reviewer: str,
        extraction_ids: tuple[str, ...],
    ) -> RequirementReviewBatchDetail:
        normalized_title = title.strip()
        normalized_reviewer = reviewer.strip()
        normalized_ids = tuple(item.strip() for item in extraction_ids if item.strip())

        if not normalized_title:
            raise InvalidRequirementReviewBatchError("title must not be blank")
        if not normalized_reviewer:
            raise InvalidRequirementReviewBatchError("reviewer must not be blank")
        if not 1 <= len(normalized_ids) <= MAX_BATCH_SIZE:
            raise InvalidRequirementReviewBatchError(
                f"extractionIds must contain between 1 and {MAX_BATCH_SIZE} items"
            )
        if len(set(normalized_ids)) != len(normalized_ids):
            raise InvalidRequirementReviewBatchError(
                "extractionIds must not contain duplicates"
            )

        snapshots = self._repository.get_extraction_snapshots(normalized_ids)
        by_id = {item.extraction_id: item for item in snapshots}
        missing = [item for item in normalized_ids if item not in by_id]
        if missing:
            raise InvalidRequirementReviewBatchError(
                f"Requirement Extractions were not found: {', '.join(missing)}"
            )
        ordered = tuple(by_id[item] for item in normalized_ids)
        stale = [item.extraction_id for item in ordered if not item.is_current]
        if stale:
            raise InvalidRequirementReviewBatchError(
                "Only the latest Requirement Extraction for each Job may enter a new batch: "
                + ", ".join(stale)
            )

        cohort = {
            (
                item.provider,
                item.model,
                item.extractor_version,
                item.prompt_version,
            )
            for item in ordered
        }
        if len(cohort) != 1:
            raise InvalidRequirementReviewBatchError(
                "All selected Extractions must share provider, model, extractorVersion and promptVersion"
            )
        provider, model, extractor_version, prompt_version = next(iter(cohort))

        batch_id = f"reqreviewbatch_{uuid4().hex}"
        write = RequirementReviewBatchWrite(
            batch_id=batch_id,
            title=normalized_title,
            reviewer=normalized_reviewer,
            provider=provider,
            model=model,
            extractor_version=extractor_version,
            prompt_version=prompt_version,
            cases=tuple(
                RequirementReviewBatchCaseWrite(
                    case_id=f"reqreviewcase_{uuid4().hex}",
                    case_index=index,
                    job_id=item.job_id,
                    extraction_id=item.extraction_id,
                )
                for index, item in enumerate(ordered)
            ),
        )
        with self._uow_factory() as uow:
            uow.reviews.add_batch(write)
            uow.commit()

        detail = self._repository.get_batch(batch_id)
        if detail is None:  # pragma: no cover - defensive persistence invariant
            raise RuntimeError(f"Persisted Requirement Review Batch {batch_id} cannot be read")
        return detail


class ListRequirementReviewBatchesUseCase:
    def __init__(self, repository: AbstractRequirementReviewQueryRepository) -> None:
        self._repository = repository

    def execute(self, *, limit: int, offset: int) -> RequirementReviewBatchPage:
        return self._repository.list_batches(limit=limit, offset=offset)


class GetRequirementReviewBatchUseCase:
    def __init__(self, repository: AbstractRequirementReviewQueryRepository) -> None:
        self._repository = repository

    def execute(self, batch_id: str) -> RequirementReviewBatchDetail:
        result = self._repository.get_batch(batch_id)
        if result is None:
            raise RequirementReviewBatchNotFoundError(
                f"Requirement Review Batch {batch_id!r} was not found"
            )
        return result


class FinalizeRequirementReviewBatchUseCase:
    """Record one immutable human conclusion over complete formal evidence."""

    def __init__(
        self,
        repository: AbstractRequirementReviewQueryRepository,
        uow_factory: RequirementReviewUnitOfWorkFactory,
    ) -> None:
        self._repository = repository
        self._uow_factory = uow_factory

    def execute(
        self,
        *,
        batch_id: str,
        decision: RequirementReviewBatchFinalDecision,
        reviewer: str,
        notes: str,
    ) -> RequirementReviewBatchFinalDecisionDetail:
        batch = self._repository.get_batch(batch_id)
        if batch is None:
            raise RequirementReviewBatchNotFoundError(
                f"Requirement Review Batch {batch_id!r} was not found"
            )
        if self._repository.get_final_decision(batch_id) is not None:
            raise RequirementReviewBatchFinalDecisionAlreadyExistsError(
                f"Requirement Review Batch {batch_id!r} already has an immutable final decision"
            )

        normalized_reviewer = reviewer.strip()
        normalized_notes = notes.strip()
        if normalized_reviewer != batch.summary.reviewer:
            raise InvalidRequirementReviewBatchFinalDecisionError(
                "Final decision reviewer must match the reviewer who owns the Batch"
            )
        if len(normalized_notes) < MIN_FINAL_DECISION_NOTES:
            raise InvalidRequirementReviewBatchFinalDecisionError(
                f"notes must contain at least {MIN_FINAL_DECISION_NOTES} characters after trimming"
            )
        if not batch.summary.formal_evidence_eligible:
            raise InvalidRequirementReviewBatchFinalDecisionError(
                "Final decision requires exactly 20 reviewed, current, non-Fixture Cases"
            )
        if any(case.review is None for case in batch.cases):
            raise InvalidRequirementReviewBatchFinalDecisionError(
                "Every Batch Case must have an immutable human review"
            )

        decided_at = datetime.now(timezone.utc)
        detail = RequirementReviewBatchFinalDecisionDetail(
            id=f"reqbatchdecision_{uuid4().hex}",
            batch_id=batch.summary.id,
            decision=decision,
            reviewer=normalized_reviewer,
            notes=normalized_notes,
            sample_size=batch.summary.sample_size,
            reviewed_count=batch.summary.reviewed_count,
            accepted_count=batch.summary.accepted_count,
            rejected_count=batch.summary.rejected_count,
            stale_case_count=batch.summary.stale_case_count,
            issue_code_counts=dict(batch.issue_code_counts),
            evidence_fingerprint=_batch_evidence_fingerprint(batch),
            decided_at=decided_at,
        )
        with self._uow_factory() as uow:
            uow.reviews.add_final_decision(
                RequirementReviewBatchFinalDecisionWrite(
                    decision_id=detail.id,
                    batch_id=detail.batch_id,
                    decision=detail.decision,
                    reviewer=detail.reviewer,
                    notes=detail.notes,
                    sample_size=detail.sample_size,
                    reviewed_count=detail.reviewed_count,
                    accepted_count=detail.accepted_count,
                    rejected_count=detail.rejected_count,
                    stale_case_count=detail.stale_case_count,
                    issue_code_counts=dict(detail.issue_code_counts),
                    evidence_fingerprint=detail.evidence_fingerprint,
                    decided_at=detail.decided_at,
                )
            )
            uow.commit()

        persisted = self._repository.get_final_decision(batch.summary.id)
        if persisted is None:  # pragma: no cover - defensive persistence invariant
            raise RuntimeError(
                f"Persisted final decision for Requirement Review Batch {batch.summary.id!r} cannot be read"
            )
        return persisted


class GetAcceptedRequirementReviewBaselineUseCase:
    def __init__(
        self,
        repository: AbstractRequirementReviewQueryRepository,
    ) -> None:
        self._repository = repository

    def execute(self) -> AcceptedRequirementReviewBaseline:
        result = self._repository.get_accepted_baseline()
        if result is None:
            raise AcceptedRequirementReviewBaselineNotFoundError(
                "No current human-accepted Requirement Review baseline exists"
            )
        return result


class ReviewRequirementBatchCaseUseCase:
    def __init__(
        self,
        repository: AbstractRequirementReviewQueryRepository,
        uow_factory: RequirementReviewUnitOfWorkFactory,
    ) -> None:
        self._repository = repository
        self._uow_factory = uow_factory

    def execute(
        self,
        *,
        batch_id: str,
        case_id: str,
        decision: RequirementReviewDecision,
        issue_codes: tuple[RequirementReviewIssueCode, ...],
        notes: str,
    ) -> RequirementReviewCaseReviewDetail:
        case = self._repository.get_case(batch_id=batch_id, case_id=case_id)
        if case is None:
            if self._repository.get_batch(batch_id) is None:
                raise RequirementReviewBatchNotFoundError(
                    f"Requirement Review Batch {batch_id!r} was not found"
                )
            raise RequirementReviewCaseNotFoundError(
                f"Requirement Review Case {case_id!r} was not found in Batch {batch_id!r}"
            )
        if case.review is not None:
            raise RequirementReviewCaseAlreadyReviewedError(
                f"Requirement Review Case {case_id!r} already has an immutable review"
            )

        normalized_notes = notes.strip()
        if len(normalized_notes) < MIN_REVIEW_NOTES:
            raise InvalidRequirementCaseReviewError(
                f"notes must contain at least {MIN_REVIEW_NOTES} characters after trimming"
            )
        if len(set(issue_codes)) != len(issue_codes):
            raise InvalidRequirementCaseReviewError(
                "issueCodes must not contain duplicates"
            )
        if decision is RequirementReviewDecision.ACCEPTED and issue_codes:
            raise InvalidRequirementCaseReviewError(
                "accepted case reviews must not contain issueCodes"
            )
        if decision is RequirementReviewDecision.REJECTED and not issue_codes:
            raise InvalidRequirementCaseReviewError(
                "rejected case reviews require at least one issueCode"
            )

        reviewed_at = datetime.now(timezone.utc)
        review_id = f"reqcasereview_{uuid4().hex}"
        with self._uow_factory() as uow:
            uow.reviews.add_case_review(
                RequirementReviewCaseReviewWrite(
                    review_id=review_id,
                    batch_case_id=case_id,
                    decision=decision,
                    issue_codes=issue_codes,
                    notes=normalized_notes,
                    reviewed_at=reviewed_at,
                )
            )
            uow.commit()

        detail = self._repository.get_case_review(case_id)
        if detail is None:  # pragma: no cover - defensive persistence invariant
            raise RuntimeError(f"Persisted Requirement Case Review {review_id} cannot be read")
        return detail


def _batch_evidence_fingerprint(batch: RequirementReviewBatchDetail) -> str:
    cases = []
    for case in sorted(batch.cases, key=lambda item: item.case_index):
        review = case.review
        if review is None:  # guarded by the final-decision policy
            continue
        cases.append(
            {
                "caseId": case.id,
                "caseIndex": case.case_index,
                "jobId": case.job_id,
                "extractionId": case.extraction_id,
                "traceRunId": case.trace_run_id,
                "descriptionSha256": sha256(
                    (case.description or "").encode("utf-8")
                ).hexdigest(),
                "isCurrent": case.is_current,
                "reviewId": review.id,
                "reviewDecision": review.decision.value,
                "issueCodes": [item.value for item in review.issue_codes],
                "reviewNotesSha256": sha256(review.notes.encode("utf-8")).hexdigest(),
                "reviewedAt": review.reviewed_at.isoformat(),
            }
        )
    payload = {
        "schemaVersion": FINAL_DECISION_EVIDENCE_SCHEMA_VERSION,
        "batchId": batch.summary.id,
        "cohort": {
            "provider": batch.summary.provider,
            "model": batch.summary.model,
            "extractorVersion": batch.summary.extractor_version,
            "promptVersion": batch.summary.prompt_version,
        },
        "summary": {
            "sampleSize": batch.summary.sample_size,
            "reviewedCount": batch.summary.reviewed_count,
            "acceptedCount": batch.summary.accepted_count,
            "rejectedCount": batch.summary.rejected_count,
            "staleCaseCount": batch.summary.stale_case_count,
            "issueCodeCounts": dict(sorted(batch.issue_code_counts.items())),
        },
        "cases": cases,
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(canonical.encode("utf-8")).hexdigest()

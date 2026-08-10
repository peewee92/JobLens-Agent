"""TargetCohort domain contract for v0.2."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class TargetCohortSelectionSource(StrEnum):
    MANUAL = "manual"
    USER_FEEDBACK = "user_feedback"


@dataclass(frozen=True, slots=True)
class TargetCohortFeedbackSource:
    feedback_id: str
    match_report_id: str
    job_id: str

    def __post_init__(self) -> None:
        normalized_feedback_id = self.feedback_id.strip()
        normalized_match_report_id = self.match_report_id.strip()
        normalized_job_id = self.job_id.strip()
        if not normalized_feedback_id:
            raise ValueError("feedback_id must not be blank")
        if not normalized_match_report_id:
            raise ValueError("match_report_id must not be blank")
        if not normalized_job_id:
            raise ValueError("job_id must not be blank")
        object.__setattr__(self, "feedback_id", normalized_feedback_id)
        object.__setattr__(self, "match_report_id", normalized_match_report_id)
        object.__setattr__(self, "job_id", normalized_job_id)


@dataclass(frozen=True, slots=True)
class TargetCohortSnapshot:
    id: str
    name: str
    selection_source: TargetCohortSelectionSource
    job_ids: tuple[str, ...]
    sample_size: int
    created_from_feedback: tuple[TargetCohortFeedbackSource, ...] = ()

    @classmethod
    def create(
        cls,
        *,
        cohort_id: str,
        name: str,
        selection_source: TargetCohortSelectionSource,
        job_ids: tuple[str, ...],
        created_from_feedback: tuple[TargetCohortFeedbackSource, ...] = (),
    ) -> "TargetCohortSnapshot":
        normalized_id = cohort_id.strip()
        normalized_name = name.strip()
        if not normalized_id:
            raise ValueError("cohort_id must not be blank")
        if not normalized_name:
            raise ValueError("name must not be blank")

        normalized_job_ids: list[str] = []
        seen_job_ids: set[str] = set()
        for job_id in job_ids:
            normalized_job_id = job_id.strip()
            if not normalized_job_id:
                raise ValueError("job_ids must not contain blank values")
            if normalized_job_id in seen_job_ids:
                continue
            seen_job_ids.add(normalized_job_id)
            normalized_job_ids.append(normalized_job_id)
        if not normalized_job_ids:
            raise ValueError("job_ids must not be empty")

        if selection_source is TargetCohortSelectionSource.USER_FEEDBACK:
            provenance_job_ids = [item.job_id for item in created_from_feedback]
            if len(provenance_job_ids) != len(set(provenance_job_ids)):
                raise ValueError("feedback provenance must contain one item per job")
            if set(provenance_job_ids) != set(normalized_job_ids):
                raise ValueError("feedback provenance must cover cohort job_ids exactly")
        elif created_from_feedback:
            raise ValueError("manual cohort must not claim feedback provenance")

        return cls(
            id=normalized_id,
            name=normalized_name,
            selection_source=selection_source,
            job_ids=tuple(normalized_job_ids),
            sample_size=len(normalized_job_ids),
            created_from_feedback=created_from_feedback,
        )


__all__ = [
    "TargetCohortFeedbackSource",
    "TargetCohortSelectionSource",
    "TargetCohortSnapshot",
]

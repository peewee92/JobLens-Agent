"""Transient Target Cohort Gap Detail HTTP endpoint."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import (
    get_target_cohort_candidates_use_case,
    get_target_cohort_gap_query_use_case,
)
from app.api.v1.schemas import ApiErrorResponse
from app.api.v1.schemas.target_cohort_gaps import (
    TargetCohortCandidatesResponse,
    TargetCohortGapRequest,
    TargetCohortGapResponse,
)
from app.application.create_target_cohort import (
    CreateFeedbackTargetCohortCommand,
    CreateManualTargetCohortCommand,
)
from app.application.target_cohort_candidates import ListTargetCohortCandidatesUseCase
from app.application.target_cohort_gap_query import (
    BuildSelectedFeedbackTargetCohortGapDetailsUseCase,
)

router = APIRouter(prefix="/target-cohort/gaps")


@router.get("/candidates", response_model=TargetCohortCandidatesResponse)
def list_target_cohort_candidates(
    use_case: Annotated[
        ListTargetCohortCandidatesUseCase,
        Depends(get_target_cohort_candidates_use_case),
    ],
) -> TargetCohortCandidatesResponse:
    return TargetCohortCandidatesResponse.from_result(use_case.execute())


@router.post(
    "",
    response_model=TargetCohortGapResponse,
    responses={409: {"model": ApiErrorResponse}},
)
def build_target_cohort_gaps(
    payload: TargetCohortGapRequest,
    use_case: Annotated[
        BuildSelectedFeedbackTargetCohortGapDetailsUseCase,
        Depends(get_target_cohort_gap_query_use_case),
    ],
) -> TargetCohortGapResponse:
    command = (
        CreateManualTargetCohortCommand(
            cohort_id=payload.cohort_id,
            name=payload.name,
            selected_job_ids=tuple(payload.selected_job_ids),
        )
        if payload.selected_job_ids
        else CreateFeedbackTargetCohortCommand(
            cohort_id=payload.cohort_id,
            name=payload.name,
            selected_feedback_ids=tuple(payload.selected_feedback_ids),
        )
    )
    result = use_case.execute(command)
    return TargetCohortGapResponse.from_result(result)

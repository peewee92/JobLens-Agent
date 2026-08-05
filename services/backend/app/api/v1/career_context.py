"""HTTP adapters for confirmed Profile and SearchIntent versions."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import (
    get_career_context_release_readiness_use_case,
    get_get_profile_use_case,
    get_get_search_intent_use_case,
    get_save_profile_use_case,
    get_save_search_intent_use_case,
)
from app.api.v1.schemas import ApiErrorResponse
from app.api.v1.schemas.career_context import (
    CareerContextReleaseReadinessResponse,
    ProfileResponse,
    SaveProfileRequest,
    SaveSearchIntentRequest,
    SearchIntentResponse,
)
from app.application.career_context.release import (
    GetCareerContextReleaseReadinessUseCase,
)
from app.application.career_context.use_cases import (
    GetProfileUseCase,
    GetSearchIntentUseCase,
    SaveProfileUseCase,
    SaveSearchIntentUseCase,
)

router = APIRouter()


@router.get(
    "/career-context/release-readiness",
    response_model=CareerContextReleaseReadinessResponse,
)
def get_career_context_release_readiness(
    use_case: Annotated[
        GetCareerContextReleaseReadinessUseCase,
        Depends(get_career_context_release_readiness_use_case),
    ],
) -> CareerContextReleaseReadinessResponse:
    return CareerContextReleaseReadinessResponse.from_detail(use_case.execute())


@router.get(
    "/profile",
    response_model=ProfileResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {"model": ApiErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ApiErrorResponse},
    },
)
def get_profile(
    use_case: Annotated[GetProfileUseCase, Depends(get_get_profile_use_case)],
) -> ProfileResponse:
    return ProfileResponse.from_detail(use_case.execute())


@router.put(
    "/profile",
    response_model=ProfileResponse,
    responses={
        status.HTTP_409_CONFLICT: {"model": ApiErrorResponse},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ApiErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ApiErrorResponse},
    },
)
def save_profile(
    request: SaveProfileRequest,
    use_case: Annotated[SaveProfileUseCase, Depends(get_save_profile_use_case)],
) -> ProfileResponse:
    return ProfileResponse.from_detail(use_case.execute(request.to_command()))


@router.get(
    "/search-intent",
    response_model=SearchIntentResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {"model": ApiErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ApiErrorResponse},
    },
)
def get_search_intent(
    use_case: Annotated[
        GetSearchIntentUseCase,
        Depends(get_get_search_intent_use_case),
    ],
) -> SearchIntentResponse:
    return SearchIntentResponse.from_detail(use_case.execute())


@router.put(
    "/search-intent",
    response_model=SearchIntentResponse,
    responses={
        status.HTTP_409_CONFLICT: {"model": ApiErrorResponse},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ApiErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ApiErrorResponse},
    },
)
def save_search_intent(
    request: SaveSearchIntentRequest,
    use_case: Annotated[
        SaveSearchIntentUseCase,
        Depends(get_save_search_intent_use_case),
    ],
) -> SearchIntentResponse:
    return SearchIntentResponse.from_detail(use_case.execute(request.to_command()))

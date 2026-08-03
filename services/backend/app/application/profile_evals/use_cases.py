"""Read use cases for immutable Profile Eval runs."""
from __future__ import annotations

from app.application.ports.profile_eval_repository import AbstractProfileEvalQueryRepository
from app.application.profile_evals.errors import ProfileEvalRunNotFoundError
from app.application.profile_evals.models import ProfileEvalRunDetail, ProfileEvalRunPage


class ListProfileEvalRunsUseCase:
    def __init__(self, repository: AbstractProfileEvalQueryRepository) -> None:
        self._repository = repository

    def execute(self, *, limit: int, offset: int) -> ProfileEvalRunPage:
        return self._repository.list_runs(limit=limit, offset=offset)


class GetProfileEvalRunUseCase:
    def __init__(self, repository: AbstractProfileEvalQueryRepository) -> None:
        self._repository = repository

    def execute(self, eval_run_id: str) -> ProfileEvalRunDetail:
        result = self._repository.get_run(eval_run_id)
        if result is None:
            raise ProfileEvalRunNotFoundError(
                f"Profile Eval Run {eval_run_id!r} was not found"
            )
        return result

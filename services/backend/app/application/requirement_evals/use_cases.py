"""Application read use cases for persisted Requirement Eval runs."""
from __future__ import annotations

from app.application.ports.requirement_eval_repository import (
    AbstractRequirementEvalQueryRepository,
)
from app.application.requirement_evals.errors import RequirementEvalRunNotFoundError
from app.application.requirement_evals.models import (
    RequirementEvalRunDetail,
    RequirementEvalRunPage,
)


class ListRequirementEvalRunsUseCase:
    def __init__(self, repository: AbstractRequirementEvalQueryRepository) -> None:
        self._repository = repository

    def execute(self, *, limit: int, offset: int) -> RequirementEvalRunPage:
        return self._repository.list_runs(limit=limit, offset=offset)


class GetRequirementEvalRunUseCase:
    def __init__(self, repository: AbstractRequirementEvalQueryRepository) -> None:
        self._repository = repository

    def execute(self, eval_run_id: str) -> RequirementEvalRunDetail:
        result = self._repository.get_run(eval_run_id)
        if result is None:
            raise RequirementEvalRunNotFoundError(
                f"Requirement Eval Run {eval_run_id!r} was not found"
            )
        return result

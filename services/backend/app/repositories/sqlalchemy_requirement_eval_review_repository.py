"""SQLAlchemy persistence for immutable Requirement Eval Reviews."""
from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.application.ports.requirement_eval_review_repository import (
    AbstractRequirementEvalReviewRepository,
)
from app.application.requirement_evals.errors import (
    RequirementEvalRunAlreadyReviewedError,
)
from app.application.requirement_evals.models import RequirementEvalReviewWrite
from app.db.models import RequirementEvalReviewORM


class SqlAlchemyRequirementEvalReviewRepository(
    AbstractRequirementEvalReviewRepository
):
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, review: RequirementEvalReviewWrite) -> None:
        self._session.add(
            RequirementEvalReviewORM(
                id=review.review_id,
                eval_run_id=review.eval_run_id,
                decision=review.decision.value,
                reviewer=review.reviewer,
                notes=review.notes,
                reviewed_at=review.reviewed_at,
            )
        )
        try:
            self._session.flush()
        except IntegrityError as error:
            raise RequirementEvalRunAlreadyReviewedError(
                f"Requirement Eval Run {review.eval_run_id!r} already has an immutable review"
            ) from error

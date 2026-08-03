"""SQLAlchemy persistence for immutable Profile Eval reviews."""
from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.application.ports.profile_eval_review_repository import (
    AbstractProfileEvalReviewRepository,
)
from app.application.profile_evals.errors import ProfileEvalRunAlreadyReviewedError
from app.application.profile_evals.models import ProfileEvalReviewWrite
from app.db.models import ProfileEvalReviewORM


class SqlAlchemyProfileEvalReviewRepository(AbstractProfileEvalReviewRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, review: ProfileEvalReviewWrite) -> None:
        self._session.add(
            ProfileEvalReviewORM(
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
            raise ProfileEvalRunAlreadyReviewedError(
                f"Profile Eval Run {review.eval_run_id!r} already has an immutable review"
            ) from error

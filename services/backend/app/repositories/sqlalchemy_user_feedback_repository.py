"""SQLAlchemy persistence for immutable UserFeedback history."""
from __future__ import annotations

from collections.abc import Callable
from datetime import timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.ports.user_feedback_repository import (
    AbstractUserFeedbackQueryRepository,
    AbstractUserFeedbackRepository,
)
from app.db.models import UserFeedbackORM
from app.domain.user_feedback import (
    FeedbackDecision,
    FeedbackReason,
    StoredUserFeedback,
    UserFeedbackDraft,
)

SessionFactory = Callable[[], Session]


class SqlAlchemyUserFeedbackRepository(AbstractUserFeedbackRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, feedback: UserFeedbackDraft) -> StoredUserFeedback:
        record = UserFeedbackORM(
            match_report_id=feedback.match_report_id,
            job_id=feedback.job_id,
            decision=feedback.decision.value,
            reasons=[reason.value for reason in feedback.reasons],
            note=feedback.note,
        )
        self._session.add(record)
        self._session.flush()
        self._session.refresh(record)
        return _stored(record)


class SqlAlchemyUserFeedbackQueryRepository(AbstractUserFeedbackQueryRepository):
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def get(self, feedback_id: str) -> StoredUserFeedback | None:
        with self._session_factory() as session:
            record = session.get(UserFeedbackORM, feedback_id)
            return _stored(record) if record is not None else None

    def list_for_match_report(self, match_report_id: str) -> tuple[StoredUserFeedback, ...]:
        with self._session_factory() as session:
            records = session.scalars(
                select(UserFeedbackORM)
                .where(UserFeedbackORM.match_report_id == match_report_id)
                .order_by(UserFeedbackORM.created_at.desc(), UserFeedbackORM.id.desc())
            ).all()
            return tuple(_stored(record) for record in records)

    def list_for_job(self, job_id: str) -> tuple[StoredUserFeedback, ...]:
        with self._session_factory() as session:
            records = session.scalars(
                select(UserFeedbackORM)
                .where(UserFeedbackORM.job_id == job_id)
                .order_by(UserFeedbackORM.created_at.desc(), UserFeedbackORM.id.desc())
            ).all()
            return tuple(_stored(record) for record in records)

    def list_all(self) -> tuple[StoredUserFeedback, ...]:
        with self._session_factory() as session:
            records = session.scalars(
                select(UserFeedbackORM).order_by(
                    UserFeedbackORM.created_at.desc(),
                    UserFeedbackORM.id.desc(),
                )
            ).all()
            return tuple(_stored(record) for record in records)


def _stored(record: UserFeedbackORM) -> StoredUserFeedback:
    created_at = (
        record.created_at.replace(tzinfo=timezone.utc)
        if record.created_at.tzinfo is None
        else record.created_at.astimezone(timezone.utc)
    )
    return StoredUserFeedback(
        id=record.id,
        feedback=UserFeedbackDraft.create(
            match_report_id=record.match_report_id,
            job_id=record.job_id,
            decision=FeedbackDecision(record.decision),
            reasons=tuple(FeedbackReason(value) for value in record.reasons),
            note=record.note,
        ),
        created_at=created_at,
    )

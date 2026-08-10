"""Persistence contract tests for immutable UserFeedback records."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.db.models import UserFeedbackORM
from app.domain.user_feedback import (
    FeedbackDecision,
    FeedbackReason,
    UserFeedbackDraft,
)
from app.repositories.sqlalchemy_user_feedback_repository import (
    SqlAlchemyUserFeedbackQueryRepository,
)
from app.repositories.sqlalchemy_user_feedback_unit_of_work import (
    SqlAlchemyUserFeedbackUnitOfWork,
)


def _draft(*, match_report_id: str = "match_1", job_id: str = "job_1") -> UserFeedbackDraft:
    return UserFeedbackDraft.create(
        match_report_id=match_report_id,
        job_id=job_id,
        decision=FeedbackDecision.REJECTED,
        reasons=(FeedbackReason.SKILL_GAP, FeedbackReason.WORK_MODE),
        note="缺少关键后端证据，且工作模式不符合偏好。",
    )


def _factory(tmp_path: Path) -> sessionmaker[Session]:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'user-feedback.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def test_user_feedback_repository_round_trips_frozen_decision_and_reasons(tmp_path: Path) -> None:
    factory = _factory(tmp_path)
    with SqlAlchemyUserFeedbackUnitOfWork(factory) as uow:
        saved = uow.feedback.add(_draft())
        uow.commit()

    loaded = SqlAlchemyUserFeedbackQueryRepository(factory).get(saved.id)

    assert loaded is not None
    assert loaded.id == saved.id
    assert loaded.feedback == _draft()
    assert loaded.feedback.reasons == (FeedbackReason.SKILL_GAP, FeedbackReason.WORK_MODE)


def test_user_feedback_repository_appends_history_for_same_match_report(tmp_path: Path) -> None:
    factory = _factory(tmp_path)
    with SqlAlchemyUserFeedbackUnitOfWork(factory) as uow:
        first = uow.feedback.add(_draft())
        uow.commit()
    with SqlAlchemyUserFeedbackUnitOfWork(factory) as uow:
        second = uow.feedback.add(
            UserFeedbackDraft.create(
                match_report_id="match_1",
                job_id="job_1",
                decision=FeedbackDecision.MAYBE,
                reasons=(FeedbackReason.COMPENSATION,),
            )
        )
        uow.commit()

    history = SqlAlchemyUserFeedbackQueryRepository(factory).list_for_match_report("match_1")

    assert first.id != second.id
    assert tuple(item.id for item in history) == (second.id, first.id)
    assert tuple(item.feedback.decision for item in history) == (
        FeedbackDecision.MAYBE,
        FeedbackDecision.REJECTED,
    )
    with factory() as session:
        assert len(session.scalars(select(UserFeedbackORM)).all()) == 2


def test_user_feedback_query_lists_feedback_for_job_only(tmp_path: Path) -> None:
    factory = _factory(tmp_path)
    with SqlAlchemyUserFeedbackUnitOfWork(factory) as uow:
        job_1 = uow.feedback.add(_draft(job_id="job_1"))
        uow.commit()
    with SqlAlchemyUserFeedbackUnitOfWork(factory) as uow:
        uow.feedback.add(_draft(match_report_id="match_2", job_id="job_2"))
        uow.commit()

    history = SqlAlchemyUserFeedbackQueryRepository(factory).list_for_job("job_1")

    assert tuple(item.id for item in history) == (job_1.id,)
    assert all(item.feedback.job_id == "job_1" for item in history)


def test_user_feedback_unit_of_work_rolls_back_uncommitted_feedback(tmp_path: Path) -> None:
    factory = _factory(tmp_path)
    with SqlAlchemyUserFeedbackUnitOfWork(factory) as uow:
        saved = uow.feedback.add(_draft())

    assert SqlAlchemyUserFeedbackQueryRepository(factory).get(saved.id) is None
    with factory() as session:
        assert session.scalars(select(UserFeedbackORM)).all() == []

"""Read-only schema gate tests for UserFeedback persistence."""
from sqlalchemy import create_engine

from app.application.user_feedback_persistence import check_user_feedback_persistence_readiness
from app.repositories.sqlalchemy_user_feedback_schema import (
    inspect_user_feedback_persistence_readiness,
)


def test_feedback_persistence_readiness_requires_both_match_reports_and_feedback_table() -> None:
    result = check_user_feedback_persistence_readiness(
        match_reports_ready=False,
        user_feedback_ready=False,
    )

    assert result.ready is False
    assert result.blocker_codes == (
        "match_report_persistence_not_ready",
        "user_feedback_persistence_not_ready",
    )
    assert result.db_writes == 0
    assert result.provider_calls == 0
    assert result.trace_runs_created == 0


def test_feedback_persistence_readiness_reports_only_missing_feedback_table() -> None:
    result = check_user_feedback_persistence_readiness(
        match_reports_ready=True,
        user_feedback_ready=False,
    )

    assert result.ready is False
    assert result.blocker_codes == ("user_feedback_persistence_not_ready",)


def test_feedback_persistence_readiness_is_ready_only_when_both_tables_exist() -> None:
    result = check_user_feedback_persistence_readiness(
        match_reports_ready=True,
        user_feedback_ready=True,
    )

    assert result.ready is True
    assert result.blocker_codes == ()


def test_sqlalchemy_feedback_persistence_inspection_is_read_only_and_fail_closed() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE match_reports (id TEXT PRIMARY KEY)")

    result = inspect_user_feedback_persistence_readiness(engine)

    assert result.ready is False
    assert result.blocker_codes == ("user_feedback_persistence_not_ready",)

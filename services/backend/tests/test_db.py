"""Database infrastructure smoke tests (Step 1 only).

Verifies the engine and session factory work. Real model/transaction tests
arrive with business Vertical Slices.
"""
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import SessionLocal, engine


def test_engine_created() -> None:
    assert engine is not None


def test_session_create_and_close() -> None:
    with SessionLocal() as session:
        assert isinstance(session, Session)
        # Session is usable within the context.
        assert session.execute(text("SELECT 1")).scalar_one() == 1
        assert session._transaction is not None
    # After the context exits, the transaction is closed (connection returned).
    assert session._transaction is None

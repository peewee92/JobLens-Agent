"""FastAPI dependency providers (Dependency Injection)."""
from collections.abc import Iterator

from sqlalchemy.orm import Session

from app.db.session import SessionLocal


def get_db() -> Iterator[Session]:
    """One Session per request. FastAPI injects this into endpoints."""
    with SessionLocal() as session:
        yield session

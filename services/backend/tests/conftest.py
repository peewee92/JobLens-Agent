"""Shared pytest fixtures.

Set the test DATABASE_URL BEFORE importing app modules so the engine is
built against an isolated SQLite database, not the dev one.
"""
import os

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", "sqlite:///./data/test_joblens.db")

import pytest
from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def db_session():
    with SessionLocal() as session:
        yield session

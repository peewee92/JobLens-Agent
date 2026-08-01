"""Declarative base for all ORM models (SQLAlchemy 2.x style)."""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass

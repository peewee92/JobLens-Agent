"""Request-scoped database selection. Never change the process-wide local database."""
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class DatabaseContext:
    engine: Engine
    sessions: Callable[[], Session]
    directory: Path


current_database: ContextVar[DatabaseContext | None] = ContextVar('joblens_database', default=None)

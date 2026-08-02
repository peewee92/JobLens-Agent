"""Import all ORM models so SQLAlchemy and Alembic can register metadata.

Alembic autogenerate only sees tables that have been imported onto Base.metadata.
Adding a model file without importing it here makes migrations silently miss it.
"""
from app.db.models.job import JobORM
from app.db.models.job_import import JobImportORM
from app.db.models.job_import_item import JobImportItemORM
from app.db.models.job_source import JobSourceORM

__all__ = [
    "JobORM",
    "JobImportORM",
    "JobImportItemORM",
    "JobSourceORM",
]

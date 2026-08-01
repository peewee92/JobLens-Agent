"""Repository layer: how business data is read/written.

Application code calls e.g. `job_repository.save(job)` and never writes
raw SQL. Concrete ORM models live in app.db.models.
"""

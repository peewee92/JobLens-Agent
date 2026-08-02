"""Architecture guards for the HTTP-to-Application boundary."""
from __future__ import annotations

import ast
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
JOB_IMPORT_ROUTE = BACKEND_ROOT / "app" / "api" / "v1" / "job_imports.py"
JOB_IMPORT_SCHEMAS = (
    BACKEND_ROOT / "app" / "api" / "v1" / "schemas" / "job_imports.py"
)


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def _called_attributes(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }


def test_job_import_route_does_not_import_persistence_details() -> None:
    imported = _imported_modules(JOB_IMPORT_ROUTE)
    forbidden_prefixes = (
        "sqlalchemy",
        "app.db",
        "app.repositories",
        "app.application.ports",
    )

    assert not any(
        module.startswith(forbidden_prefixes) for module in imported
    )


def test_job_import_route_does_not_manage_transactions() -> None:
    calls = _called_attributes(JOB_IMPORT_ROUTE)

    # The only allowed ``execute`` is ImportJobsUseCase.execute(). Transaction
    # methods must never appear in the HTTP adapter.
    assert "execute" in calls
    assert calls.isdisjoint({"commit", "rollback", "flush", "add"})


def test_public_api_schemas_do_not_import_persistence_details() -> None:
    imported = _imported_modules(JOB_IMPORT_SCHEMAS)

    assert not any(
        module.startswith(("sqlalchemy", "app.db", "app.repositories"))
        for module in imported
    )

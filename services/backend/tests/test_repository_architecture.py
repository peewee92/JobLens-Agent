"""Small architecture guards for persistence boundaries."""
from __future__ import annotations

import ast
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PORTS_DIR = BACKEND_ROOT / "app" / "application" / "ports"
SQLALCHEMY_REPOSITORY = (
    BACKEND_ROOT / "app" / "repositories" / "sqlalchemy_job_repository.py"
)
IMPORT_USE_CASE = (
    BACKEND_ROOT / "app" / "application" / "job_imports" / "use_case.py"
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


def test_application_ports_do_not_import_sqlalchemy() -> None:
    imported = set()
    for path in PORTS_DIR.glob("*.py"):
        imported.update(_imported_modules(path))

    assert not any(module.startswith("sqlalchemy") for module in imported)


def test_import_use_case_does_not_import_sqlalchemy_or_orm_models() -> None:
    imported = _imported_modules(IMPORT_USE_CASE)

    assert not any(module.startswith("sqlalchemy") for module in imported)
    assert not any(module.startswith("app.db.models") for module in imported)


def test_sqlalchemy_repository_does_not_own_commit_or_rollback() -> None:
    tree = ast.parse(SQLALCHEMY_REPOSITORY.read_text(encoding="utf-8"))
    transaction_calls = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"commit", "rollback"}
    }

    assert transaction_calls == set()

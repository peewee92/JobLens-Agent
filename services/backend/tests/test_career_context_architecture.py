"""Architecture guards for the career-context slice."""
from __future__ import annotations

import ast
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
APPLICATION_DIR = BACKEND_ROOT / "app" / "application" / "career_context"
PORTS = (
    BACKEND_ROOT / "app" / "application" / "ports" / "career_context_repository.py",
    BACKEND_ROOT / "app" / "application" / "ports" / "career_context_unit_of_work.py",
)
ROUTER = BACKEND_ROOT / "app" / "api" / "v1" / "career_context.py"
REPOSITORY = (
    BACKEND_ROOT
    / "app"
    / "repositories"
    / "sqlalchemy_career_context_repository.py"
)


def _tree(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"))


def _imports(path: Path) -> set[str]:
    result: set[str] = set()
    for node in ast.walk(_tree(path)):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module)
    return result


def test_career_application_and_ports_do_not_import_frameworks() -> None:
    paths = [*APPLICATION_DIR.glob("*.py"), *PORTS]
    imported = {module for path in paths for module in _imports(path)}

    assert not any(module.startswith("sqlalchemy") for module in imported)
    assert not any(module.startswith("fastapi") for module in imported)
    assert not any(module.startswith("app.db") for module in imported)
    assert not any(module.startswith("app.repositories") for module in imported)


def test_career_router_does_not_import_repository_orm_or_session() -> None:
    imported = _imports(ROUTER)

    assert not any(module.startswith("sqlalchemy") for module in imported)
    assert not any(module.startswith("app.db") for module in imported)
    assert not any(module.startswith("app.repositories") for module in imported)


def test_career_router_does_not_manage_transactions() -> None:
    forbidden = {
        node.func.attr
        for node in ast.walk(_tree(ROUTER))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"add", "flush", "commit", "rollback", "delete"}
    }
    assert forbidden == set()


def test_career_repository_never_commits_or_rolls_back() -> None:
    forbidden = {
        node.func.attr
        for node in ast.walk(_tree(REPOSITORY))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"commit", "rollback"}
    }
    assert forbidden == set()

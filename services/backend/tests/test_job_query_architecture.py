"""Architecture guards for the Job Pool read path."""
from __future__ import annotations

import ast
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
APPLICATION_DIR = BACKEND_ROOT / "app" / "application" / "job_queries"
PORT = BACKEND_ROOT / "app" / "application" / "ports" / "job_query_repository.py"
ROUTER = BACKEND_ROOT / "app" / "api" / "v1" / "jobs.py"
QUERY_REPOSITORY = (
    BACKEND_ROOT / "app" / "repositories" / "sqlalchemy_job_query_repository.py"
)


def _tree(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"))


def _imports(path: Path) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(_tree(path)):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_query_application_and_port_do_not_import_sqlalchemy() -> None:
    paths = [*APPLICATION_DIR.glob("*.py"), PORT]
    imported = {module for path in paths for module in _imports(path)}

    assert not any(module.startswith("sqlalchemy") for module in imported)
    assert not any(module.startswith("app.db") for module in imported)
    assert not any(module.startswith("app.repositories") for module in imported)


def test_job_router_does_not_import_repository_orm_or_session() -> None:
    imported = _imports(ROUTER)

    assert not any(module.startswith("sqlalchemy") for module in imported)
    assert not any(module.startswith("app.db") for module in imported)
    assert not any(module.startswith("app.repositories") for module in imported)


def test_job_router_does_not_manage_transactions() -> None:
    forbidden = {
        node.func.attr
        for node in ast.walk(_tree(ROUTER))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"add", "flush", "commit", "rollback", "delete"}
    }

    assert forbidden == set()


def test_query_repository_does_not_write_or_manage_transactions() -> None:
    forbidden = {
        node.func.attr
        for node in ast.walk(_tree(QUERY_REPOSITORY))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"add", "add_all", "flush", "commit", "rollback", "delete"}
    }

    assert forbidden == set()

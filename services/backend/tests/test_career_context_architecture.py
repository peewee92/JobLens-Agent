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
RELEASE_POLICY = APPLICATION_DIR / "release.py"


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


def test_release_policy_uses_confirmed_context_not_llm_eval_or_trace() -> None:
    imported = _imports(RELEASE_POLICY)
    forbidden = (
        "app.application.profile_evals",
        "app.application.ports.profile_eval",
        "app.evals",
        "app.llm",
        "app.workflows",
        "app.application.ports.trace",
    )
    assert not any(
        module.startswith(prefix)
        for module in imported
        for prefix in forbidden
    )

    router_source = ROUTER.read_text(encoding="utf-8")
    assert "profile_skill_evidence_missing" not in router_source
    assert "search_intent_target_roles_missing" not in router_source


def test_career_router_does_not_manage_transactions() -> None:
    forbidden = {
        node.func.attr
        for node in ast.walk(_tree(ROUTER))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"add", "flush", "commit", "rollback", "delete"}
    }
    assert forbidden == set()


def test_release_snapshot_selects_profile_and_intent_ids_together() -> None:
    source = REPOSITORY.read_text(encoding="utf-8")
    assert "def get_current_context" in source
    assert "select(profile_id_query, intent_id_query)" in source
    assert "CareerContextSnapshot" in source


def test_career_repository_never_commits_or_rolls_back() -> None:
    forbidden = {
        node.func.attr
        for node in ast.walk(_tree(REPOSITORY))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"commit", "rollback"}
    }
    assert forbidden == set()

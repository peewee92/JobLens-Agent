"""Architecture guards for the first LLM-backed workflow."""
from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
APPLICATION_DIR = BACKEND_ROOT / "app" / "application" / "profile_extraction"
WORKFLOW = BACKEND_ROOT / "app" / "workflows" / "profile_extraction.py"
ROUTER = BACKEND_ROOT / "app" / "api" / "v1" / "profile_proposals.py"
TRACE_REPOSITORY = (
    BACKEND_ROOT / "app" / "repositories" / "sqlalchemy_trace_repository.py"
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


def test_profile_extraction_application_is_framework_free() -> None:
    imported = {
        module
        for path in APPLICATION_DIR.glob("*.py")
        for module in _imports(path)
    }

    assert not any(module.startswith("sqlalchemy") for module in imported)
    assert not any(module.startswith("fastapi") for module in imported)
    assert not any(module.startswith("app.db") for module in imported)
    assert not any(module.startswith("app.repositories") for module in imported)


def test_profile_extraction_workflow_does_not_confirm_profile_or_import_frameworks() -> None:
    imported = _imports(WORKFLOW)
    source = WORKFLOW.read_text(encoding="utf-8")

    assert not any(module.startswith("sqlalchemy") for module in imported)
    assert not any(module.startswith("fastapi") for module in imported)
    assert not any(module.startswith("app.db") for module in imported)
    assert "SaveProfileUseCase" not in source
    assert "save_profile" not in source


def test_profile_proposal_router_uses_workflow_not_llm_or_repository() -> None:
    imported = _imports(ROUTER)

    assert not any(module.startswith("app.llm") for module in imported)
    assert not any(module.startswith("app.repositories") for module in imported)
    assert not any(module.startswith("app.db") for module in imported)
    assert not any(module.startswith("sqlalchemy") for module in imported)


def test_profile_eval_entrypoint_imports_in_a_clean_python_process() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from app.evals import run_profile_eval; "
            "from scripts.run_profile_eval import main; "
            "assert callable(run_profile_eval) and callable(main)",
        ],
        cwd=BACKEND_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_trace_repository_never_commits_or_rolls_back() -> None:
    forbidden = {
        node.func.attr
        for node in ast.walk(_tree(TRACE_REPOSITORY))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"commit", "rollback"}
    }

    assert forbidden == set()

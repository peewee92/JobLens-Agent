"""Architecture guards for Requirement Eval execution and read APIs."""
from __future__ import annotations

import ast
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _source(path: str) -> str:
    return (BACKEND_ROOT / path).read_text(encoding="utf-8")


def _imports(path: str) -> set[str]:
    tree = ast.parse(_source(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_requirement_eval_execution_does_not_import_sqlalchemy_or_orm_models() -> None:
    for path in [
        "app/evals/job_requirement_extraction.py",
        "app/evals/requirement_eval_runs.py",
        "app/application/requirement_evals/models.py",
        "app/application/requirement_evals/use_cases.py",
    ]:
        imports = _imports(path)
        assert not any(module.startswith("sqlalchemy") for module in imports), path
        assert not any(module.startswith("app.db.models") for module in imports), path


def test_requirement_eval_router_does_not_run_provider_or_touch_repositories() -> None:
    imports = _imports("app/api/v1/requirement_evals.py")
    forbidden_prefixes = (
        "app.llm",
        "app.repositories",
        "app.db",
        "sqlalchemy",
    )
    assert not any(
        module.startswith(prefix)
        for module in imports
        for prefix in forbidden_prefixes
    )


def test_requirement_eval_repositories_do_not_manage_transactions() -> None:
    for path in [
        "app/repositories/sqlalchemy_requirement_eval_repository.py",
        "app/repositories/sqlalchemy_requirement_eval_review_repository.py",
    ]:
        tree = ast.parse(_source(path))
        forbidden_calls = {"commit", "rollback", "delete"}
        calls = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        assert not (calls & forbidden_calls), path


def test_requirement_release_eligibility_requires_live_mode_and_gate_pass() -> None:
    source = _source("app/evals/requirement_eval_runs.py")
    assert "RequirementEvalMode.LIVE and report.gate_passed" in source


def test_requirement_eval_read_contract_does_not_expose_raw_jd() -> None:
    source = _source("app/api/v1/schemas/requirement_evals.py")
    assert "description" not in source
    assert "original_text" not in source
    assert "evidence_span" not in source


def test_requirement_eval_use_cases_remain_application_only() -> None:
    imports = _imports("app/application/requirement_evals/use_cases.py")
    forbidden_prefixes = ("fastapi", "sqlalchemy", "app.db", "app.repositories")
    assert not any(
        module.startswith(prefix)
        for module in imports
        for prefix in forbidden_prefixes
    )


def test_requirement_eval_router_does_not_implement_review_policy() -> None:
    source = _source("app/api/v1/requirement_evals.py")
    for forbidden in ["release_eligible", "gate_passed", "mode ==", "mode !="]:
        assert forbidden not in source

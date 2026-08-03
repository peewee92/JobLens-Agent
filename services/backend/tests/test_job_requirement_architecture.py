"""Architecture guards for Job Requirement Extraction."""
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


def test_requirement_application_does_not_import_http_sqlalchemy_or_orm() -> None:
    for path in [
        "app/application/job_requirements/models.py",
        "app/application/job_requirements/errors.py",
        "app/application/job_requirements/validation.py",
        "app/application/job_requirements/use_cases.py",
        "app/evals/job_requirement_extraction.py",
    ]:
        imports = _imports(path)
        forbidden = ("fastapi", "sqlalchemy", "app.db", "app.repositories")
        assert not any(
            module.startswith(prefix)
            for module in imports
            for prefix in forbidden
        ), path


def test_requirement_router_only_calls_application_use_cases() -> None:
    imports = _imports("app/api/v1/job_requirements.py")
    forbidden = ("app.llm", "app.repositories", "app.db", "sqlalchemy")
    assert not any(
        module.startswith(prefix)
        for module in imports
        for prefix in forbidden
    )


def test_requirement_workflow_does_not_import_orm_or_repository() -> None:
    imports = _imports("app/workflows/job_requirement_extraction.py")
    forbidden = ("app.db", "app.repositories", "sqlalchemy", "fastapi")
    assert not any(
        module.startswith(prefix)
        for module in imports
        for prefix in forbidden
    )


def test_requirement_repository_does_not_manage_transactions() -> None:
    source = _source("app/repositories/sqlalchemy_job_requirement_repository.py")
    tree = ast.parse(source)
    forbidden_calls = {"commit", "rollback", "delete"}
    calls = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert not (calls & forbidden_calls)


def test_requirement_api_contract_does_not_return_full_job_description() -> None:
    source = _source("app/api/v1/schemas/job_requirements.py")
    assert "description:" not in source
    assert "source_raw" not in source
    assert "canonical_key" not in source

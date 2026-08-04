"""Architecture guards for Requirement manual review batches."""
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


def test_requirement_review_application_and_ports_are_framework_free() -> None:
    for path in [
        "app/application/requirement_reviews/models.py",
        "app/application/requirement_reviews/use_cases.py",
        "app/application/ports/requirement_review_repository.py",
        "app/application/ports/requirement_review_unit_of_work.py",
    ]:
        imports = _imports(path)
        forbidden = ("fastapi", "sqlalchemy", "app.db", "app.repositories")
        assert not any(
            module.startswith(prefix)
            for module in imports
            for prefix in forbidden
        ), path


def test_requirement_review_router_only_calls_application_use_cases() -> None:
    imports = _imports("app/api/v1/requirement_reviews.py")
    forbidden = ("app.llm", "app.repositories", "app.db", "sqlalchemy")
    assert not any(
        module.startswith(prefix)
        for module in imports
        for prefix in forbidden
    )
    source = _source("app/api/v1/requirement_reviews.py")
    assert "openai" not in source.casefold()
    assert "FixtureJobRequirementExtractor" not in source


def test_requirement_review_repository_does_not_manage_transactions() -> None:
    tree = ast.parse(
        _source("app/repositories/sqlalchemy_requirement_review_repository.py")
    )
    forbidden_calls = {"commit", "rollback", "delete"}
    calls = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert not (calls & forbidden_calls)


def test_review_contract_exposes_required_evidence_without_storage_secrets() -> None:
    source = _source("app/api/v1/schemas/requirement_reviews.py")
    assert "description" in source
    assert "JobRequirementResponse" in source
    for forbidden in [
        "source_raw",
        "candidate_raw",
        "canonical_key",
        "input_hash",
        "api_key",
        "provider_request",
    ]:
        assert forbidden not in source.casefold()


def test_formal_evidence_rule_is_derived_in_read_model() -> None:
    source = _source("app/repositories/sqlalchemy_requirement_review_repository.py")
    assert "FORMAL_REVIEW_SAMPLE_SIZE = 20" in source
    assert "stale_count == 0" in source
    assert 'batch.provider.casefold() != "fixture"' in source
    assert "formal_evidence_eligible" not in _source(
        "app/db/models/requirement_review.py"
    )

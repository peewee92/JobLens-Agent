"""Architecture guards for the read-only Requirement readiness dashboard."""
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


def test_dashboard_application_does_not_import_provider_http_or_orm() -> None:
    imports = _imports(
        "app/application/requirement_acceptance/readiness_dashboard.py"
    )
    forbidden = ("fastapi", "app.llm", "app.db", "app.repositories")
    assert not any(
        module.startswith(prefix)
        for module in imports
        for prefix in forbidden
    )


def test_dashboard_router_exposes_only_get_readiness() -> None:
    source = _source("app/api/v1/requirement_acceptance_runs.py")
    readiness_section = source.split('@router.get(\n    "/readiness"', 1)[1].split(
        '@router.get(\n    "/{run_id}"', 1
    )[0]

    assert "@router.get" not in readiness_section
    assert "@router.post" not in readiness_section
    assert "execute-canary" not in readiness_section
    assert "OPENAI_API_KEY" not in readiness_section
    assert "requirement-extractions" not in readiness_section


def test_dashboard_response_excludes_paths_commands_and_secret_values() -> None:
    source = _source("app/api/v1/schemas/requirement_acceptance_runs.py")
    dashboard_section = source.split(
        "class RequirementAcceptanceReadinessResponse", 1
    )[1].split("class RequirementAcceptanceCanaryReviewRequest", 1)[0]

    assert "dataset_path" not in dashboard_section
    assert "private_root" not in dashboard_section
    assert "recommended_command" not in dashboard_section
    assert "api_key:" not in dashboard_section
    assert "api_key_configured" in dashboard_section
    assert "db_writes" in dashboard_section
    assert "provider_calls" in dashboard_section

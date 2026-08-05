"""Architecture guards for Match input preflight."""
from __future__ import annotations

import ast
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
APPLICATION = BACKEND_ROOT / "app" / "application" / "match_inputs" / "readiness.py"
ROUTER = BACKEND_ROOT / "app" / "api" / "v1" / "job_requirements.py"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(item.name for item in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module)
    return result


def test_match_input_application_is_framework_and_provider_free() -> None:
    imported = _imports(APPLICATION)
    assert not any(name.startswith("fastapi") for name in imported)
    assert not any(name.startswith("sqlalchemy") for name in imported)
    assert not any(name.startswith("app.llm") for name in imported)
    assert not any(name.startswith("app.workflows") for name in imported)
    assert not any(name.startswith("app.tracing") for name in imported)


def test_router_delegates_without_reimplementing_gate_policy() -> None:
    source = ROUTER.read_text(encoding="utf-8")
    assert "GetMatchInputReadinessUseCase" in source
    assert "inputs_release_eligible=" not in source
    assert "release_eligible and" not in source
    assert "provider_calls" not in source

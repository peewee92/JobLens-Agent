"""Architecture guards for resume-document ingestion."""
from __future__ import annotations

import ast
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
APPLICATION_DIR = BACKEND_ROOT / "app" / "application" / "resume_documents"
PORT = BACKEND_ROOT / "app" / "application" / "ports" / "resume_document_parser.py"
PARSER = BACKEND_ROOT / "app" / "document_parsers" / "resume_document_parser.py"
WORKFLOW = BACKEND_ROOT / "app" / "workflows" / "resume_document_proposal.py"
ROUTER = BACKEND_ROOT / "app" / "api" / "v1" / "profile_proposals.py"


def imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module)
    return result


def test_resume_document_application_and_port_are_framework_free() -> None:
    imported = {
        module
        for path in [*APPLICATION_DIR.glob("*.py"), PORT]
        for module in imports(path)
    }
    assert not any(module.startswith("fastapi") for module in imported)
    assert not any(module.startswith("sqlalchemy") for module in imported)
    assert not any(module.startswith("pypdf") for module in imported)
    assert not any(module.startswith("app.document_parsers") for module in imported)


def test_parser_is_deterministic_infrastructure_not_ai_or_persistence() -> None:
    imported = imports(PARSER)
    assert not any(module.startswith("fastapi") for module in imported)
    assert not any(module.startswith("app.llm") for module in imported)
    assert not any(module.startswith("app.repositories") for module in imported)
    assert not any(module.startswith("app.db") for module in imported)


def test_document_workflow_composes_parser_and_proposal_without_confirming_profile() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    imported = imports(WORKFLOW)
    assert "SaveProfileUseCase" not in source
    assert "save_profile" not in source
    assert not any(module.startswith("fastapi") for module in imported)
    assert not any(module.startswith("sqlalchemy") for module in imported)
    assert not any(module.startswith("app.repositories") for module in imported)


def test_router_does_not_import_pdf_docx_or_parser_implementation() -> None:
    imported = imports(ROUTER)
    assert not any(module.startswith("pypdf") for module in imported)
    assert not any(module.startswith("zipfile") for module in imported)
    assert not any(module.startswith("app.document_parsers") for module in imported)

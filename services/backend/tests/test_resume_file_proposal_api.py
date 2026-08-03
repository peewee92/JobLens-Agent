"""HTTP integration tests for PDF/DOCX Profile Proposal uploads."""
from __future__ import annotations

from collections.abc import Iterator
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_profile_document_workflow
from app.application.resume_documents import MAX_RESUME_FILE_BYTES
from app.db.base import Base
from app.db.models import TraceSpanORM, UserProfileORM
from app.document_parsers import ResumeDocumentParser
from app.llm import FixtureProfileExtractor
from app.main import app
from app.repositories import SqlAlchemyTraceUnitOfWork
from app.workflows import (
    ProposeProfileFromDocumentWorkflow,
    ProposeProfileFromResumeWorkflow,
)


def make_docx() -> bytes:
    document_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:body>
<w:p><w:r><w:t>8 年前端开发经验，负责 React 与 TypeScript 业务开发。</w:t></w:r></w:p>
<w:p><w:r><w:t>项目经历：构建 JobLens Agent，使用 FastAPI 和 Next.js。</w:t></w:r></w:p>
<w:p><w:r><w:t>参与 Agent 工作流、Evidence 校验和 Trace 落地。</w:t></w:r></w:p>
</w:body></w:document>"""
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", document_xml)
        archive.writestr("custom/binary-marker.bin", b"ORIGINAL-FILE-ONLY-MARKER")
    return output.getvalue()


@pytest.fixture
def file_api_environment(
    tmp_path: Path,
) -> Iterator[tuple[TestClient, sessionmaker[Session]]]:
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'resume-file-api.db'}"
    )

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    profile_workflow = ProposeProfileFromResumeWorkflow(
        FixtureProfileExtractor(),
        lambda: SqlAlchemyTraceUnitOfWork(factory),
    )
    app.dependency_overrides[get_profile_document_workflow] = lambda: (
        ProposeProfileFromDocumentWorkflow(ResumeDocumentParser(), profile_workflow)
    )
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client, factory
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def count_rows(factory: sessionmaker[Session], model: type) -> int:
    with factory() as session:
        return int(session.scalar(select(func.count()).select_from(model)) or 0)


def test_docx_upload_returns_proposal_without_confirming_profile(
    file_api_environment: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = file_api_environment

    response = client.post(
        "/api/v1/profile-proposals/file",
        files={
            "file": (
                "resume.docx",
                make_docx(),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["runId"].startswith("run_")
    assert {item["name"] for item in body["skills"]} >= {
        "React",
        "TypeScript",
        "Agent",
        "FastAPI",
        "Next.js",
    }
    assert count_rows(factory, TraceSpanORM) == 1
    assert count_rows(factory, UserProfileORM) == 0

    with factory() as session:
        trace = session.scalar(select(TraceSpanORM))
        assert trace is not None
        serialized = repr({
            "input_refs": trace.input_refs,
            "output": trace.output,
            "error": trace.error,
        })
        assert "ORIGINAL-FILE-ONLY-MARKER" not in serialized
        assert "resume.docx" not in serialized
        assert set(trace.input_refs) == {"resumeSha256", "characterCount"}


def test_missing_file_returns_stable_422_without_trace(
    file_api_environment: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = file_api_environment

    response = client.post("/api/v1/profile-proposals/file", files={})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_resume_document"
    assert count_rows(factory, TraceSpanORM) == 0


def test_spoofed_pdf_returns_415_without_trace(
    file_api_environment: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = file_api_environment

    response = client.post(
        "/api/v1/profile-proposals/file",
        files={"file": ("resume.pdf", b"not-pdf", "application/pdf")},
    )

    assert response.status_code == 415
    assert response.json()["error"]["code"] == "unsupported_resume_document"
    assert count_rows(factory, TraceSpanORM) == 0


def test_scanned_pdf_returns_422_without_trace(
    file_api_environment: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = file_api_environment
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    output = BytesIO()
    writer.write(output)

    response = client.post(
        "/api/v1/profile-proposals/file",
        files={"file": ("scan.pdf", output.getvalue(), "application/pdf")},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "resume_text_not_extractable"
    assert count_rows(factory, TraceSpanORM) == 0


def test_oversized_upload_returns_413_before_parser(
    file_api_environment: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = file_api_environment

    response = client.post(
        "/api/v1/profile-proposals/file",
        files={
            "file": (
                "resume.pdf",
                b"%PDF-" + b"x" * MAX_RESUME_FILE_BYTES,
                "application/pdf",
            )
        },
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "resume_document_too_large"
    assert count_rows(factory, TraceSpanORM) == 0


def test_openapi_documents_file_proposal_errors(
    file_api_environment: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, _factory = file_api_environment

    operation = client.get("/openapi.json").json()["paths"][
        "/api/v1/profile-proposals/file"
    ]["post"]

    assert operation["responses"]["200"]
    assert operation["responses"]["413"]
    assert operation["responses"]["415"]
    assert operation["responses"]["422"]

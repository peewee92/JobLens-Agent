"""Byte-level tests for PDF/DOCX resume parsing boundaries."""
from __future__ import annotations

from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.application.resume_documents import (
    InvalidResumeDocumentError,
    MAX_PDF_PAGES,
    MAX_RESUME_FILE_BYTES,
    ResumeDocumentInput,
    ResumeDocumentTooLargeError,
    ResumeTextNotExtractableError,
    UnsupportedResumeDocumentError,
)
from app.document_parsers import ResumeDocumentParser


def make_text_pdf(text: str) -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    font_ref = writer._add_object(font)
    page[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject(
                {NameObject("/F1"): font_ref}
            )
        }
    )
    stream = DecodedStreamObject()
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream.set_data(f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET".encode("latin-1"))
    page[NameObject("/Contents")] = writer._add_object(stream)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def make_docx() -> bytes:
    document_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:r><w:t>8 years frontend engineering with React and TypeScript.</w:t></w:r></w:p>
    <w:tbl>
      <w:tr><w:tc><w:p><w:r><w:t>Project</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>JobLens Agent</w:t></w:r></w:p></w:tc></w:tr>
      <w:tr><w:tc><w:p><w:r><w:t>Result</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>Built FastAPI and Next.js workflow.</w:t></w:r></w:p></w:tc></w:tr>
    </w:tbl>
    <w:p><w:r><w:t>Implemented evidence-grounded Profile extraction.</w:t></w:r></w:p>
  </w:body>
</w:document>"""
    content_types = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("word/document.xml", document_xml)
    return output.getvalue()


def test_pdf_parser_extracts_text() -> None:
    parser = ResumeDocumentParser()
    parsed = parser.parse(
        ResumeDocumentInput(
            filename="resume.pdf",
            content_type="application/pdf",
            content=make_text_pdf(
                "8 years frontend engineering. Built React TypeScript Agent applications."
            ),
        )
    )

    assert parsed.document_type == "pdf"
    assert parsed.page_count == 1
    assert "React TypeScript Agent" in parsed.text


def test_docx_parser_preserves_paragraph_and_table_order() -> None:
    parsed = ResumeDocumentParser().parse(
        ResumeDocumentInput(
            filename="resume.docx",
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            content=make_docx(),
        )
    )

    assert parsed.document_type == "docx"
    assert parsed.page_count is None
    assert parsed.text.splitlines() == [
        "8 years frontend engineering with React and TypeScript.",
        "Project | JobLens Agent",
        "Result | Built FastAPI and Next.js workflow.",
        "Implemented evidence-grounded Profile extraction.",
    ]


def test_empty_or_scanned_pdf_is_rejected() -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    output = BytesIO()
    writer.write(output)

    with pytest.raises(ResumeTextNotExtractableError):
        ResumeDocumentParser().parse(
            ResumeDocumentInput("scan.pdf", "application/pdf", output.getvalue())
        )


def test_encrypted_pdf_is_rejected() -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.encrypt("secret")
    output = BytesIO()
    writer.write(output)

    with pytest.raises(InvalidResumeDocumentError, match="Encrypted PDF"):
        ResumeDocumentParser().parse(
            ResumeDocumentInput("resume.pdf", "application/pdf", output.getvalue())
        )


def test_pdf_page_limit_is_enforced() -> None:
    writer = PdfWriter()
    for _ in range(MAX_PDF_PAGES + 1):
        writer.add_blank_page(width=612, height=792)
    output = BytesIO()
    writer.write(output)

    with pytest.raises(InvalidResumeDocumentError, match="page"):
        ResumeDocumentParser().parse(
            ResumeDocumentInput("resume.pdf", "application/pdf", output.getvalue())
        )


def test_forged_extension_and_content_type_are_rejected() -> None:
    parser = ResumeDocumentParser()
    with pytest.raises(UnsupportedResumeDocumentError):
        parser.parse(
            ResumeDocumentInput("resume.pdf", "application/pdf", b"not a pdf")
        )
    with pytest.raises(UnsupportedResumeDocumentError):
        parser.parse(
            ResumeDocumentInput(
                "resume.docx", "application/pdf", make_docx()
            )
        )


def test_file_size_limit_is_enforced() -> None:
    with pytest.raises(ResumeDocumentTooLargeError):
        ResumeDocumentParser().parse(
            ResumeDocumentInput(
                "resume.pdf",
                "application/pdf",
                b"%PDF-" + b"x" * MAX_RESUME_FILE_BYTES,
            )
        )

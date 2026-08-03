"""PDF/DOCX implementation of the resume-document parsing port."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.application.ports.resume_document_parser import AbstractResumeDocumentParser
from app.application.resume_documents import (
    InvalidResumeDocumentError,
    MAX_DOCX_XML_BYTES,
    MAX_PDF_PAGE_CONTENT_BYTES,
    MAX_PDF_PAGES,
    MAX_RESUME_FILE_BYTES,
    ParsedResumeDocument,
    ResumeDocumentInput,
    ResumeDocumentTooLargeError,
    UnsupportedResumeDocumentError,
    normalize_extracted_text,
)

PDF_CONTENT_TYPES = {None, "", "application/pdf", "application/octet-stream"}
DOCX_CONTENT_TYPES = {
    None,
    "",
    "application/octet-stream",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


class ResumeDocumentParser(AbstractResumeDocumentParser):
    """Detect the actual document structure and extract normalized text."""

    def parse(self, document: ResumeDocumentInput) -> ParsedResumeDocument:
        if not document.content:
            raise InvalidResumeDocumentError("Resume document is empty.")
        if len(document.content) > MAX_RESUME_FILE_BYTES:
            raise ResumeDocumentTooLargeError(
                f"Resume document exceeds {MAX_RESUME_FILE_BYTES} bytes."
            )

        suffix = Path(document.filename or "").suffix.lower()
        if suffix == ".pdf":
            self._require_content_type(document.content_type, PDF_CONTENT_TYPES, "PDF")
            if not document.content.startswith(b"%PDF-"):
                raise UnsupportedResumeDocumentError(
                    "File extension is .pdf but the content is not a PDF."
                )
            return self._parse_pdf(document)

        if suffix == ".docx":
            self._require_content_type(document.content_type, DOCX_CONTENT_TYPES, "DOCX")
            if not document.content.startswith(b"PK"):
                raise UnsupportedResumeDocumentError(
                    "File extension is .docx but the content is not an Office Open XML document."
                )
            return self._parse_docx(document)

        raise UnsupportedResumeDocumentError(
            "Only .pdf and .docx resume documents are supported."
        )

    @staticmethod
    def _require_content_type(
        content_type: str | None,
        allowed: set[str | None],
        document_type: str,
    ) -> None:
        normalized = content_type.lower().split(";", 1)[0].strip() if content_type else None
        if normalized not in allowed:
            raise UnsupportedResumeDocumentError(
                f"Declared content type is not compatible with {document_type}."
            )

    def _parse_pdf(self, document: ResumeDocumentInput) -> ParsedResumeDocument:
        try:
            reader = PdfReader(BytesIO(document.content), strict=False)
            if reader.is_encrypted:
                raise InvalidResumeDocumentError("Encrypted PDF resumes are not supported.")
            page_count = len(reader.pages)
            if page_count == 0:
                raise InvalidResumeDocumentError("PDF contains no pages.")
            if page_count > MAX_PDF_PAGES:
                raise InvalidResumeDocumentError(
                    f"PDF contains {page_count} pages; the limit is {MAX_PDF_PAGES}."
                )

            page_text: list[str] = []
            for index, page in enumerate(reader.pages):
                contents = page.get_contents()
                if contents is not None:
                    expanded = contents.get_data()
                    if len(expanded) > MAX_PDF_PAGE_CONTENT_BYTES:
                        raise InvalidResumeDocumentError(
                            f"PDF page {index + 1} content exceeds the safe parsing limit."
                        )
                page_text.append(page.extract_text() or "")
        except InvalidResumeDocumentError:
            raise
        except (PdfReadError, OSError, ValueError, TypeError) as error:
            raise InvalidResumeDocumentError("PDF could not be parsed.") from error

        text = normalize_extracted_text("\n\n".join(page_text))
        return ParsedResumeDocument(
            filename=document.filename,
            document_type="pdf",
            text=text,
            page_count=page_count,
        )

    def _parse_docx(self, document: ResumeDocumentInput) -> ParsedResumeDocument:
        try:
            with ZipFile(BytesIO(document.content)) as archive:
                names = set(archive.namelist())
                if "word/document.xml" not in names:
                    raise UnsupportedResumeDocumentError(
                        "DOCX archive does not contain word/document.xml."
                    )
                relevant_size = sum(
                    info.file_size
                    for info in archive.infolist()
                    if info.filename.startswith("word/") and info.filename.endswith(".xml")
                )
                if relevant_size > MAX_DOCX_XML_BYTES:
                    raise InvalidResumeDocumentError(
                        "Expanded DOCX XML exceeds the safe parsing limit."
                    )

                document_xml = archive.read("word/document.xml")

            root = ElementTree.fromstring(document_xml)
            namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
            body = root.find(f"{namespace}body")
            if body is None:
                raise InvalidResumeDocumentError("DOCX document body is missing.")

            blocks: list[str] = []
            for block in body:
                if block.tag == f"{namespace}p":
                    text = "".join(
                        node.text or "" for node in block.iter(f"{namespace}t")
                    ).strip()
                    if text:
                        blocks.append(text)
                elif block.tag == f"{namespace}tbl":
                    for row in block.findall(f"{namespace}tr"):
                        cells: list[str] = []
                        for cell in row.findall(f"{namespace}tc"):
                            text = "".join(
                                node.text or ""
                                for node in cell.iter(f"{namespace}t")
                            ).strip()
                            if text:
                                cells.append(text)
                        if cells:
                            blocks.append(" | ".join(cells))
        except UnsupportedResumeDocumentError:
            raise
        except InvalidResumeDocumentError:
            raise
        except (BadZipFile, ElementTree.ParseError, KeyError, OSError, ValueError) as error:
            raise InvalidResumeDocumentError("DOCX could not be parsed.") from error

        text = normalize_extracted_text("\n".join(blocks))
        return ParsedResumeDocument(
            filename=document.filename,
            document_type="docx",
            text=text,
            page_count=None,
        )

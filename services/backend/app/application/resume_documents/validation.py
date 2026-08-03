"""Shared deterministic limits and text normalization for resume documents."""
from __future__ import annotations

import re

from app.application.resume_documents.errors import ResumeTextNotExtractableError

MAX_RESUME_FILE_BYTES = 5 * 1024 * 1024
MAX_PDF_PAGES = 20
MAX_PDF_PAGE_CONTENT_BYTES = 4 * 1024 * 1024
MAX_DOCX_XML_BYTES = 10 * 1024 * 1024
MIN_RESUME_TEXT_CHARS = 50
MAX_RESUME_TEXT_CHARS = 30_000


def normalize_extracted_text(text: str) -> str:
    """Normalize document whitespace without inventing or rewriting content."""

    normalized_lines = [line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    normalized = "\n".join(normalized_lines)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized).strip()

    if len(normalized) < MIN_RESUME_TEXT_CHARS:
        raise ResumeTextNotExtractableError(
            "Resume document did not contain enough extractable text; scanned PDFs require OCR, which is not supported yet."
        )
    if len(normalized) > MAX_RESUME_TEXT_CHARS:
        raise ResumeTextNotExtractableError(
            f"Extracted resume text exceeds {MAX_RESUME_TEXT_CHARS} characters."
        )
    return normalized

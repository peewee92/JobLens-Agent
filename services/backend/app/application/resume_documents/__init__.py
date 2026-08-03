"""Resume document parsing models, errors and limits."""

from app.application.resume_documents.errors import (
    InvalidResumeDocumentError,
    ResumeDocumentError,
    ResumeDocumentTooLargeError,
    ResumeTextNotExtractableError,
    UnsupportedResumeDocumentError,
)
from app.application.resume_documents.models import (
    ParsedResumeDocument,
    ResumeDocumentInput,
)
from app.application.resume_documents.validation import (
    MAX_DOCX_XML_BYTES,
    MAX_PDF_PAGE_CONTENT_BYTES,
    MAX_PDF_PAGES,
    MAX_RESUME_FILE_BYTES,
    MAX_RESUME_TEXT_CHARS,
    MIN_RESUME_TEXT_CHARS,
    normalize_extracted_text,
)

__all__ = [
    "InvalidResumeDocumentError",
    "MAX_DOCX_XML_BYTES",
    "MAX_PDF_PAGE_CONTENT_BYTES",
    "MAX_PDF_PAGES",
    "MAX_RESUME_FILE_BYTES",
    "MAX_RESUME_TEXT_CHARS",
    "MIN_RESUME_TEXT_CHARS",
    "ParsedResumeDocument",
    "ResumeDocumentError",
    "ResumeDocumentInput",
    "ResumeDocumentTooLargeError",
    "ResumeTextNotExtractableError",
    "UnsupportedResumeDocumentError",
    "normalize_extracted_text",
]

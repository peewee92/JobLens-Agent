"""Application models for deterministic resume-document parsing."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ResumeDocumentInput:
    filename: str
    content_type: str | None
    content: bytes


@dataclass(frozen=True, slots=True)
class ParsedResumeDocument:
    filename: str
    document_type: str
    text: str
    page_count: int | None

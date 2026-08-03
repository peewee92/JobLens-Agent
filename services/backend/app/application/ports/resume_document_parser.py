"""Application-owned port for deterministic resume-document parsing."""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.application.resume_documents.models import (
    ParsedResumeDocument,
    ResumeDocumentInput,
)


class AbstractResumeDocumentParser(ABC):
    @abstractmethod
    def parse(self, document: ResumeDocumentInput) -> ParsedResumeDocument:
        """Extract normalized resume text or raise a stable document error."""

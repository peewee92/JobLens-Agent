"""Compose deterministic document parsing with the grounded Profile Proposal workflow."""
from __future__ import annotations

from app.application.ports.resume_document_parser import AbstractResumeDocumentParser
from app.application.profile_extraction import ProfileExtractionProposal
from app.application.resume_documents import ResumeDocumentInput
from app.workflows.profile_extraction import ProposeProfileFromResumeWorkflow


class ProposeProfileFromDocumentWorkflow:
    def __init__(
        self,
        parser: AbstractResumeDocumentParser,
        profile_workflow: ProposeProfileFromResumeWorkflow,
    ) -> None:
        self._parser = parser
        self._profile_workflow = profile_workflow

    def execute(self, document: ResumeDocumentInput) -> ProfileExtractionProposal:
        parsed = self._parser.parse(document)
        return self._profile_workflow.execute(parsed.text)

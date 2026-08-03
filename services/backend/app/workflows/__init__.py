"""Stable business workflows."""

from app.workflows.profile_extraction import ProposeProfileFromResumeWorkflow
from app.workflows.resume_document_proposal import ProposeProfileFromDocumentWorkflow

__all__ = [
    "ProposeProfileFromDocumentWorkflow",
    "ProposeProfileFromResumeWorkflow",
]

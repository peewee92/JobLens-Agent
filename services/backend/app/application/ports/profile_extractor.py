"""Application-owned Profile Extractor capability port."""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.application.profile_extraction.models import ProfileExtractorResult


class AbstractProfileExtractor(ABC):
    """Produce structured candidate facts from resume text.

    Implementations may call an external LLM, replay fixtures, or use another
    provider. They must not persist confirmed Profile data.
    """

    @property
    @abstractmethod
    def model_name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def extract(self, resume_text: str) -> ProfileExtractorResult:
        raise NotImplementedError

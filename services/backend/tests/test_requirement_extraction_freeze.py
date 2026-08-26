"""MVP freeze guard for Requirement Extraction semantic versions."""
from __future__ import annotations

from app.application.job_requirements.release import MVP_FROZEN_EXTRACTOR_VERSION
from app.application.job_requirements.validation import SEMANTIC_POLICY_VERSION
from app.workflows.job_requirement_extraction import EXTRACTOR_VERSION


FROZEN_MVP_EXTRACTOR_VERSION = "requirement-extractor-v42.95"
FROZEN_MVP_SEMANTIC_POLICY_VERSION = "requirement-semantics-v42.95"


def test_requirement_extraction_versions_remain_frozen_for_mvp() -> None:
    """Ordinary MVP work must not silently resume extraction semantic tuning."""

    assert EXTRACTOR_VERSION == FROZEN_MVP_EXTRACTOR_VERSION
    assert MVP_FROZEN_EXTRACTOR_VERSION == FROZEN_MVP_EXTRACTOR_VERSION
    assert SEMANTIC_POLICY_VERSION == FROZEN_MVP_SEMANTIC_POLICY_VERSION

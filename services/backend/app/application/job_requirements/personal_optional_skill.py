"""Keep explicit optional skill notes from becoming must-haves in local extraction."""
from __future__ import annotations

import re
from dataclasses import replace

from app.application.job_requirements.models import JobRequirementExtractionOutput
from app.application.job_requirements.validation import _unique_exact_span
from app.domain.job_requirements import RequirementImportance, RequirementType

POLICY = "personal-optional-skill-v1"
# Match only a direct statement about the same name. Never classify a whole
# compound requirement based on a word such as "advantage" anywhere in the line.
_OPTIONAL_TAIL = (
    r"\s+(?:(?:is\s+)?(?:advantageous|helpful|a\s+plus|an\s+advantage))"
    r"(?:\s*,\s*|\s+but\s+)not\s+(?:mandatory|required)"
)
_PARENTHETICAL = re.compile(r"\(([^()\n]+)\)|（([^（）\n]+)）")


def preserve_explicit_optional_skill(
    description: str,
    output: JobRequirementExtractionOutput,
) -> tuple[JobRequirementExtractionOutput, tuple[int, ...]]:
    repairs: list[int] = []
    items = list(output.requirements)
    for index, item in enumerate(items):
        if item.type is not RequirementType.SKILL or item.importance is not RequirementImportance.MUST_HAVE:
            continue
        skill = (item.normalized_capability or "").strip()
        evidence = item.evidence_span.strip()
        original = item.original_text.strip()
        if (
            not skill or len(skill) > 100
            or _unique_exact_span(description, evidence) is None
            or _unique_exact_span(evidence, original) is None
        ):
            continue
        text = original.rstrip(".。").strip()
        pattern = re.compile(re.escape(skill) + _OPTIONAL_TAIL, re.IGNORECASE)
        explicit = pattern.fullmatch(text) is not None
        if not explicit and text.casefold() == skill.casefold():
            explicit = any(
                pattern.fullmatch((part.group(1) or part.group(2)).strip()) is not None
                for part in _PARENTHETICAL.finditer(evidence)
            )
        if explicit:
            items[index] = replace(item, importance=RequirementImportance.PREFERRED)
            repairs.append(index)
    return (replace(output, requirements=tuple(items)), tuple(repairs)) if repairs else (output, ())

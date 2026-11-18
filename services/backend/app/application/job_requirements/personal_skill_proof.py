"""Preserve an exact skill when a posting also asks the candidate to explain their work."""
import re
from dataclasses import replace

from app.application.job_requirements.models import JobRequirementExtractionOutput
from app.application.job_requirements.validation import (
    _ALTERNATIVE_GROUP_PATTERN, _SOFT_MARKER_PATTERN, _is_requirement_section_span,
    _unique_exact_span,
)
from app.domain.job_requirements import RequirementImportance, RequirementType

POLICY = "personal-skill-proof-v1"
SKILL_AND_PROOF = re.compile(
    r"(?:(?:任职要求|岗位要求|基本要求|要求)\s*[:：]\s*)?"
    r"(?:熟练掌握|熟练使用|熟悉|掌握|精通)\s*(?P<skill>[\w+#.\- ]{1,48}?)"
    r"\s*[,，]\s*(?:能够|能|可以)(?:以[^，,；;。]{1,24})?"
    r"(?:说明|讲解|描述)[^，,；;。]{2,80}[。.]?"
)
NON_SINGLE_CAPABILITY = re.compile(r"或者|或|以及|及|以及|与|和|等|其中|至少|以上|不限|优先|加分")


def preserve_skill_requiring_proof(description: str, output: JobRequirementExtractionOutput):
    """Narrow user-product rule; leave frozen model-evaluation extraction untouched.

    The clause is anchored verbatim in the requirement section. A single skill with
    a request to explain it is not a compound constraint. Keep the whole clause and
    its importance; never promote a qualification, alternative, or bonus.
    """
    items = list(output.requirements)
    repaired = []
    for index, item in enumerate(items):
        if item.type is not RequirementType.CONSTRAINT or item.normalized_capability is not None:
            continue
        if item.importance is not RequirementImportance.MUST_HAVE:
            continue
        raw = item.original_text.strip()
        if (_unique_exact_span(description, raw) is None
                or not _is_requirement_section_span(description, item.evidence_span)
                or _ALTERNATIVE_GROUP_PATTERN.search(raw) or _SOFT_MARKER_PATTERN.search(raw)):
            continue
        match = SKILL_AND_PROOF.fullmatch(raw)
        if not match:
            continue
        skill = match.group("skill").strip()
        if not skill or NON_SINGLE_CAPABILITY.search(skill):
            continue
        if any(other.type is RequirementType.SKILL and other.normalized_capability == skill
               and (other.original_text in raw or raw in other.original_text)
               for other in output.requirements):
            continue
        items[index] = replace(item, type=RequirementType.SKILL, normalized_capability=skill)
        repaired.append(index)
    return replace(output, requirements=tuple(items)), tuple(repaired)

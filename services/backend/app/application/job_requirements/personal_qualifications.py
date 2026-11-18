"""Preserve explicit qualification relationships without deciding personal eligibility."""
from __future__ import annotations

import re
from dataclasses import replace

from app.application.job_requirements.models import JobRequirementDetail, JobRequirementExtractionOutput
from app.application.job_requirements.validation import MAX_REQUIREMENTS_PER_RUN, _unique_exact_span
from app.domain.job_requirements import RequirementImportance, RequirementType

POLICY = "personal-quals-v1"

_REQUIRED_HEADER = re.compile(
    r"^\s*(?:required(?: qualifications)?|minimum qualifications|要求|任职要求|必备条件)\s*[:：]",
    re.IGNORECASE,
)
_NONREQUIRED_SECTION = re.compile(
    r"(?:preferred(?: qualifications)?|nice to have|optional|bonus|优先|加分|非必需)\s*[:：]",
    re.IGNORECASE,
)
_NONREQUIRED_WORDING = re.compile(r"优先|加分|非必需|不要求|不限|最好|可选")
_DEGREE_EQUIVALENCE = re.compile(
    r"(?:a\s+)?(?:relevant\s+)?(?:bachelor['’]s|master['’]s) degree"
    r"(?: may be substituted with | or )"
    r"(?:comparable|equivalent) (?:hands-on |practical |work )?experience[.]?"
    r"|[^。；;，,：:\n]{0,36}(?:本科学历|本科学位|硕士学历|硕士学位|本科|硕士)"
    r"\s*或\s*(?:同等|等效)(?:实践(?:经验)?|(?:工作|相关)?经验)",
    re.IGNORECASE,
)
# Only two explicit, conjunctive qualifications. Do not generalize an "and" in
# prose, locations with alternatives, or a note about the employer's sponsorship policy.
_RESIDENCY = (
    r"(?:candidates|applicants) must (?:live|reside|be based) in "
    r"(?:(?!\b(?:and|or|but)\b)[a-z]+(?:[-'][a-z]+)* )*[a-z]+"
)
_AUTHORIZATION = r"(?:hold|have|possess) (?:valid )?(?:(?!no |not )[a-z]{2,3} )?work authori[sz]ation"
_RESIDENCY_AND_AUTHORIZATION = re.compile(
    rf"(?P<residency>{_RESIDENCY}) and (?P<authorization>{_AUTHORIZATION})[.]?", re.IGNORECASE,
)


def qualification_review_reason(row: JobRequirementDetail) -> str | None:
    """Do not infer a sensitive or alternative qualification from arbitrary career text."""
    if row.type is not RequirementType.CONSTRAINT or POLICY not in row.extractor_version.split("+"):
        return None
    quote = row.original_text.strip()
    if _DEGREE_EQUIVALENCE.fullmatch(quote) and not _NONREQUIRED_WORDING.search(quote):
        return "学历或等效实践满足其一即可；是否等效需结合岗位和已确认经历核实。"
    if re.fullmatch(_RESIDENCY, quote, re.IGNORECASE):
        return "这是岗位的居住地要求，不能从求职地点或零散经历推断。请核实实际居住情况。"
    if re.fullmatch(_AUTHORIZATION, quote, re.IGNORECASE):
        return "这是岗位的工作授权要求，不能从居住地或经历推断。请核实岗位要求与你的情况。"
    if _RESIDENCY_AND_AUTHORIZATION.fullmatch(quote):
        return "居住地和工作授权是不同要求，不能从零散经历推断。请分别核实。"
    return None


def preserve_grounded_qualifications(
    description: str,
    output: JobRequirementExtractionOutput,
) -> tuple[JobRequirementExtractionOutput, tuple[tuple[int, str], ...]]:
    items = []
    repairs = []
    available_rows = MAX_REQUIREMENTS_PER_RUN - len(output.requirements)
    identities = {(row.type, row.original_text, row.importance) for row in output.requirements}
    for index, row in enumerate(output.requirements):
        quote = row.original_text.strip()
        evidence = row.evidence_span.strip()
        anchor = _unique_exact_span(evidence, quote)
        if anchor is None or _unique_exact_span(description, evidence) is None:
            items.append(row)
            continue
        if row.type in (RequirementType.EDUCATION, RequirementType.CONSTRAINT):
            prefix = evidence[:anchor[0]]
            must_header = _REQUIRED_HEADER.match(prefix)
            if (
                must_header is not None and not _NONREQUIRED_SECTION.search(prefix)
                and not _NONREQUIRED_WORDING.search(quote)
                and _DEGREE_EQUIVALENCE.fullmatch(quote)
                and (row.type is not RequirementType.CONSTRAINT or row.importance is not RequirementImportance.MUST_HAVE)
            ):
                # One gate with two routes; neither a hard degree requirement
                # nor an unconditional pass. Eligibility still needs evidence.
                items.append(replace(row, type=RequirementType.CONSTRAINT,
                    importance=RequirementImportance.MUST_HAVE, normalized_capability=None))
                repairs.append((index, "preserve_degree_or_practice"))
                continue
        if (
            row.type is RequirementType.CONSTRAINT
            and row.importance is RequirementImportance.MUST_HAVE
            and row.normalized_capability is None
            and (match := _RESIDENCY_AND_AUTHORIZATION.fullmatch(quote)) is not None
        ):
            missing = [match[name] for name in ("residency", "authorization")
                       if (row.type, match[name], row.importance) not in identities]
            if len(missing) - 1 > available_rows:
                items.append(row)  # Keep the exact compound quote at the size limit.
                continue
            available_rows -= len(missing) - 1
            for clause in missing:
                items.append(replace(row, original_text=clause))
                identities.add((row.type, clause, row.importance))
            repairs.append((index, "separate_residency_and_work_authorization"))
            continue
        items.append(row)
    return (replace(output, requirements=tuple(items)), tuple(repairs)) if repairs else (output, ())

"""Deterministic capability normalization for released TargetCohort facts."""
from __future__ import annotations

from dataclasses import dataclass
import re

from app.application.target_cohort_requirement_aggregation import (
    TargetCohortRequirementAggregationResult,
    TargetCohortRequirementBlocker,
)
from app.domain.job_requirements import RequirementImportance, RequirementType


_EXPLICIT_CAPABILITY_ALIASES: dict[str, str] = {
    "react": "React",
    "react.js": "React",
    "reactjs": "React",
    "node.js": "Node.js",
    "nodejs": "Node.js",
    "next.js": "Next.js",
    "nextjs": "Next.js",
    "vue.js": "Vue.js",
    "vuejs": "Vue.js",
}

_EXPLICIT_MEMBER_SCOPE_MARKERS = (
    "包括但不限于",
    "任意一种",
    "任意一个",
    "任一种",
    "任一个",
    "任一",
    "至少一个",
    "至少一种",
    "之一",
    "including but not limited to",
    "such as",
    "for example",
    "e.g.",
    "e.g",
    "any one",
    "one of",
    "either",
)
_EXAMPLE_CATEGORY_SCOPE = re.compile(
    r"等[^，,。；;]{0,24}(?:平台|框架|技术栈|工具|概念|能力|语言|数据库|模型|协议|实践经验)",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class TargetCohortCapability:
    capability: str
    source_capabilities: tuple[str, ...]
    requirement_ids: tuple[str, ...]
    job_ids: tuple[str, ...]
    requirement_count: int
    job_count: int
    must_have_count: int
    preferred_count: int
    bonus_count: int
    member_options: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class TargetCohortCapabilityNormalizationResult:
    cohort_id: str
    job_ids: tuple[str, ...]
    facts_usable: bool
    capabilities: tuple[TargetCohortCapability, ...]
    blockers: tuple[TargetCohortRequirementBlocker, ...]
    db_writes: int = 0
    provider_calls: int = 0
    trace_runs_created: int = 0


@dataclass(slots=True)
class _CapabilityAccumulator:
    capability: str
    source_capabilities: list[str]
    requirement_ids: list[str]
    job_ids: list[str]
    must_have_count: int = 0
    preferred_count: int = 0
    bonus_count: int = 0
    member_options: list[str] | None = None


class NormalizeTargetCohortCapabilitiesUseCase:
    """Normalize only explicit aliases from already released skill facts.

    Unknown capability labels are preserved as-is. This intentionally avoids fuzzy or
    semantic merging so downstream Skill Gap metrics remain traceable to original
    JobRequirement facts rather than inferred equivalence.
    """

    def execute(
        self,
        aggregation: TargetCohortRequirementAggregationResult,
    ) -> TargetCohortCapabilityNormalizationResult:
        if not aggregation.facts_usable:
            return TargetCohortCapabilityNormalizationResult(
                cohort_id=aggregation.cohort_id,
                job_ids=aggregation.job_ids,
                facts_usable=False,
                capabilities=(),
                blockers=aggregation.blockers,
            )

        accumulators: dict[str, _CapabilityAccumulator] = {}
        for fact in aggregation.requirements:
            if fact.type is not RequirementType.SKILL or fact.normalized_capability is None:
                continue

            source_capability = fact.normalized_capability.strip()
            if not source_capability:
                continue
            capability = canonicalize_target_cohort_capability(source_capability)
            accumulator = accumulators.get(capability)
            if accumulator is None:
                accumulator = _CapabilityAccumulator(
                    capability=capability,
                    source_capabilities=[],
                    requirement_ids=[],
                    job_ids=[],
                    member_options=[],
                )
                accumulators[capability] = accumulator

            if source_capability not in accumulator.source_capabilities:
                accumulator.source_capabilities.append(source_capability)
            for member in _explicit_member_options(fact.original_text, source_capability):
                if member not in accumulator.member_options:
                    accumulator.member_options.append(member)
            accumulator.requirement_ids.append(fact.requirement_id)
            if fact.job_id not in accumulator.job_ids:
                accumulator.job_ids.append(fact.job_id)

            if fact.importance is RequirementImportance.MUST_HAVE:
                accumulator.must_have_count += 1
            elif fact.importance is RequirementImportance.PREFERRED:
                accumulator.preferred_count += 1
            elif fact.importance is RequirementImportance.BONUS:
                accumulator.bonus_count += 1

        capabilities = tuple(
            TargetCohortCapability(
                capability=item.capability,
                source_capabilities=tuple(item.source_capabilities),
                requirement_ids=tuple(item.requirement_ids),
                job_ids=tuple(item.job_ids),
                requirement_count=len(item.requirement_ids),
                job_count=len(item.job_ids),
                must_have_count=item.must_have_count,
                preferred_count=item.preferred_count,
                bonus_count=item.bonus_count,
                member_options=tuple(item.member_options or ()),
            )
            for item in accumulators.values()
        )
        return TargetCohortCapabilityNormalizationResult(
            cohort_id=aggregation.cohort_id,
            job_ids=aggregation.job_ids,
            facts_usable=True,
            capabilities=capabilities,
            blockers=(),
        )


def _explicit_member_options(original_text: str, capability: str) -> tuple[str, ...]:
    """Expose exact list members only when the JD explicitly declares option/example scope.

    This is deliberately narrower than generic tokenization. A plain conjunctive
    requirement such as ``Python、Java`` remains one capability unless the source
    text itself says the list is optional/alternative/example-based.
    """
    scope = original_text.casefold()
    if not any(marker in scope for marker in _EXPLICIT_MEMBER_SCOPE_MARKERS) and not _EXAMPLE_CATEGORY_SCOPE.search(original_text):
        return ()

    split_pattern = r"\s*[,，、]\s*"
    if capability.count("/") >= 2:
        split_pattern = r"\s*[,，、/]\s*"
    members = [
        canonicalize_target_cohort_capability(part.strip(" `*"))
        for part in re.split(split_pattern, capability)
        if part.strip(" `*")
    ]
    members = list(dict.fromkeys(members))
    return tuple(members) if len(members) >= 2 else ()


def canonicalize_target_cohort_capability(value: str) -> str:
    """Return the stable canonical label for an explicitly approved alias."""
    return _EXPLICIT_CAPABILITY_ALIASES.get(value.strip().casefold(), value.strip())


__all__ = [
    "NormalizeTargetCohortCapabilitiesUseCase",
    "canonicalize_target_cohort_capability",
    "TargetCohortCapability",
    "TargetCohortCapabilityNormalizationResult",
]

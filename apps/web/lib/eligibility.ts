import type {
  EligibilityDecision,
  RequirementEligibilityResult,
  RequirementFitStatus,
} from "@/lib/contracts";

export const eligibilityLabels: Record<EligibilityDecision, string> = {
  eligible: "基础硬条件已满足",
  conditional: "有潜力，但还需要确认",
  blocked: "当前不建议优先投入",
};

export const eligibilityDescriptions: Record<EligibilityDecision, string> = {
  eligible: "当前已确认职业背景没有发现明确的硬条件缺口。",
  conditional: "暂时没有明确硬伤，但仍有硬条件缺少足够结构化证据，需要进一步确认。",
  blocked: "当前已确认职业背景存在岗位明确硬条件的证据缺口，建议先补强或降低投入优先级。",
};

export const requirementFitLabels: Record<RequirementFitStatus, string> = {
  matched: "已匹配",
  conditional: "待确认",
  missing: "明显缺失",
};

export function groupEligibilityRequirements(
  requirements: RequirementEligibilityResult[],
): Record<RequirementFitStatus, RequirementEligibilityResult[]> {
  return {
    matched: requirements.filter((item) => item.status === "matched"),
    conditional: requirements.filter((item) => item.status === "conditional"),
    missing: requirements.filter((item) => item.status === "missing"),
  };
}

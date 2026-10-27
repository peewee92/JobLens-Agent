import type {
  EligibilityDecision,
  RequirementEligibilityResult,
  RequirementFitStatus,
} from "@/lib/contracts";

export const eligibilityLabels: Record<EligibilityDecision, string> = {
  eligible: "基础硬条件已满足",
  conditional: "有条件待核实",
  blocked: "当前不建议优先投入",
};

export const eligibilityDescriptions: Record<EligibilityDecision, string> = {
  eligible: "当前已确认职业背景没有发现明确的硬条件缺口。",
  conditional: "岗位要求或求职偏好仍有条件需要核实；没有证据不代表明确不满足。",
  blocked: "已确认事实与岗位明确硬条件冲突；这不同于没有填写技能或学历证据。",
};

export const requirementFitLabels: Record<RequirementFitStatus, string> = {
  matched: "已匹配",
  conditional: "待确认",
  missing: "明确不满足",
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

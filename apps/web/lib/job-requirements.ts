import type {
  JobRequirement,
  JobRequirementReleaseReadiness,
  RequirementImportance,
  RequirementType,
} from "@/lib/contracts";

export function requirementTypeLabel(type: RequirementType): string {
  return {
    skill: "技能",
    experience: "经验",
    education: "学历",
    responsibility: "职责",
    domain: "领域",
    constraint: "约束",
  }[type];
}

export function requirementImportanceLabel(
  importance: RequirementImportance,
): string {
  return {
    must_have: "必须",
    preferred: "优先",
    bonus: "加分",
  }[importance];
}

export type RequirementReleaseBlockerCopy = {
  title: string;
  description: string;
};

export const shortJobDescriptionGuidance = "岗位描述不足，请重新采集包含完整职责和任职要求的岗位，再进行要求分析。";
export const longJobDescriptionGuidance = "岗位描述超过分析长度上限，请检查采集内容，重新采集不超过 50000 字符的完整岗位描述后再分析。";

export function jobDescriptionIssue(description: string | null | undefined): string | null {
  // Python's len() counts Unicode code points rather than UTF-16 code units.
  const length = Array.from((description ?? "").trim()).length;
  if (length < 40) return shortJobDescriptionGuidance;
  if (length > 50_000) return longJobDescriptionGuidance;
  return null;
}

export function hasEnoughJobDescription(description: string | null | undefined): boolean {
  return jobDescriptionIssue(description) === null;
}

const requirementReleaseBlockerCopies: Record<string, RequirementReleaseBlockerCopy> = {
  accepted_baseline_missing: {
    title: "当前没有有效的岗位要求审核基线",
    description:
      "可能尚未建立审核基线，也可能原有基线已失效。仅重新分析当前岗位不能保证恢复匹配；请查看人工审核状态，或联系维护人员处理。",
  },
  requirement_extraction_missing: {
    title: "这个岗位还没有完成要求分析",
    description:
      "点击“分析岗位要求”，系统会从岗位描述中整理学历、经验、技能和职责等关键要求。",
  },
  extraction_input_stale: {
    title: "岗位内容有更新，需要重新分析",
    description: "当前分析基于旧版岗位描述。为避免用过期信息匹配，请重新分析岗位要求。",
  },
  extraction_cohort_mismatch: {
    title: "岗位分析版本与审核基线不一致",
    description: "请检查当前分析版本和人工审核基线。重新分析不一定使用相同版本，也不保证解除阻断。",
  },
  requirements_empty: {
    title: "没有识别到可用的岗位要求",
    description: "这次分析没有得到可核对的要求，建议检查岗位描述后重新分析。",
  },
  requirement_count_mismatch: {
    title: "岗位要求数据需要重新校验",
    description: "系统发现分析结果不完整，为避免错误匹配，暂时不会使用这份结果。",
  },
  trace_missing: {
    title: "岗位要求分析记录不完整",
    description: "系统缺少这次分析的验证记录，需要重新分析后才能用于匹配。",
  },
  trace_failed: {
    title: "岗位要求分析没有成功完成",
    description: "这次分析过程中出现错误，请重新分析岗位要求后再尝试匹配。",
  },
  trace_capability_mismatch: {
    title: "岗位要求分析记录需要重新校验",
    description: "系统发现分析记录类型不一致，为避免错误匹配，暂时不会使用这份结果。",
  },
  trace_cohort_mismatch: {
    title: "岗位要求分析版本不一致",
    description: "分析结果与验证记录来自不同版本，需要重新分析后才能用于匹配。",
  },
  trace_input_mismatch: {
    title: "岗位内容与分析记录不一致",
    description: "系统发现当前岗位描述与分析时的输入不一致，需要重新分析后才能用于匹配。",
  },
  trace_output_mismatch: {
    title: "岗位要求分析结果不完整",
    description: "系统发现展示的岗位要求与分析记录不一致，需要重新分析后才能用于匹配。",
  },
};

const blockersRequiringExtraction = new Set([
  "requirement_extraction_missing", "extraction_input_stale", "extraction_cohort_mismatch",
  "requirements_empty", "trace_missing", "trace_failed", "trace_cohort_mismatch",
  "trace_input_mismatch",
]);

export function requirementReleaseBlockerCopy(
  code: string,
  description?: string | null,
): RequirementReleaseBlockerCopy {
  const issue = description === undefined ? null : jobDescriptionIssue(description);
  if (blockersRequiringExtraction.has(code) && issue) {
    return {title: issue === shortJobDescriptionGuidance ? "岗位描述不足" : "岗位描述过长", description: issue};
  }
  return (
    requirementReleaseBlockerCopies[code] ?? {
      title: "岗位要求暂时还不能用于匹配",
      description: "还有一项准备工作没有完成。你可以稍后重试；如果持续出现问题，再联系维护人员检查。",
    }
  );
}

export function requirementReleaseLabel(
  readiness: JobRequirementReleaseReadiness,
): string {
  return readiness.releaseEligible
    ? "岗位要求已准备好，可用于后续匹配"
    : "岗位要求还在准备中，暂时不会用于匹配";
}

export function sortJobRequirements(
  requirements: JobRequirement[],
): JobRequirement[] {
  const order: Record<RequirementImportance, number> = {
    must_have: 0,
    preferred: 1,
    bonus: 2,
  };
  return [...requirements].sort(
    (left, right) =>
      order[left.importance] - order[right.importance] ||
      left.requirementIndex - right.requirementIndex,
  );
}

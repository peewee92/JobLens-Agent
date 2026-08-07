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

const requirementReleaseBlockerCopies: Record<string, RequirementReleaseBlockerCopy> = {
  accepted_baseline_missing: {
    title: "系统还在确认 AI 分析是否足够可靠",
    description:
      "在用于岗位匹配前，我们会先人工抽查 AI 对岗位要求的理解，避免错误分析影响推荐结果。",
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
    title: "岗位要求分析版本已更新",
    description: "当前结果来自旧的分析版本，需要重新分析后才能用于匹配。",
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

export function requirementReleaseBlockerCopy(
  code: string,
): RequirementReleaseBlockerCopy {
  return (
    requirementReleaseBlockerCopies[code] ?? {
      title: "岗位要求暂时还不能用于匹配",
      description: "系统检测到一项准备工作未完成，请稍后重试或查看技术详情。",
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

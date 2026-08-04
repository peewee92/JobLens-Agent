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

export const requirementReleaseBlockerLabels: Record<string, string> = {
  accepted_baseline_missing: "尚无当前有效的人工接受 Requirement 基线",
  requirement_extraction_missing: "该岗位尚无 Requirement Extraction",
  extraction_input_stale: "Extraction 已不对应当前 JD",
  extraction_cohort_mismatch: "Extraction 模型版本与人工接受基线不一致",
  requirements_empty: "Extraction 没有 Requirement 事实",
  requirement_count_mismatch: "Requirement 计数与实际记录不一致",
  trace_missing: "Extraction Trace 不存在",
  trace_failed: "Extraction Trace 记录了执行错误",
  trace_capability_mismatch: "Trace 不是 Requirement Extraction 能力运行",
  trace_cohort_mismatch: "Trace 模型版本与 Extraction 不一致",
  trace_input_mismatch: "Trace 输入引用与岗位或 JD 不一致",
  trace_output_mismatch: "Trace 输出数量与持久化 Requirement 不一致",
};

export function requirementReleaseLabel(
  readiness: JobRequirementReleaseReadiness,
): string {
  return readiness.releaseEligible
    ? "已通过 Requirement 事实发布门禁"
    : `不可供 Match 使用：${readiness.blockers.length} 个阻塞项`;
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

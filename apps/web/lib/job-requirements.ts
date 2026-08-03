import type {
  JobRequirement,
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

const completionCriteriaLabels: Record<string, string> = {
  confirmed_profile_skill_exists: "在已确认职业背景中补充并确认这项能力",
  confirmed_evidence_linked_to_skill_exists: "至少补充 1 条可核验的工作或项目证据，并与这项能力关联",
};

export function currentStateLabel(value: string): string {
  if (value === "missing" || value === "capability_missing") return "当前职业背景里还没有确认这项能力。";
  if (value === "skill_exists_without_confirmed_evidence") {
    return "你已经写过这项能力，但还缺少可核验的项目或工作证据。";
  }
  return value;
}

export function completionCriterionLabel(value: string): string {
  return completionCriteriaLabels[value] ?? value;
}


const completionCriteriaLabels: Record<string, string> = {
  confirmed_profile_skill_exists: "在已确认职业背景中补充并确认这项能力",
  confirmed_evidence_linked_to_skill_exists: "至少补充 1 条可核验的工作或项目证据，并与这项能力关联",
};

export function currentStateLabel(value: string): string {
  if (value === "missing" || value === "capability_missing") return "当前职业背景里还没有确认这项能力。";
  if (value === "skill_exists_without_confirmed_evidence") {
    return "你已经写过这项能力，但还缺少可核验的项目或工作证据。";
  }
  return "当前资料不足以判断覆盖情况，请核对岗位要求和已确认的经历。";
}

export function completionCriterionLabel(value: string): string {
  return completionCriteriaLabels[value] ?? "对照岗位原文核实要求与经历，不能确认的请留空。";
}


/** Use only frozen facts. Legacy priorities alone cannot tell whether a posting required a skill. */
export function gapImportanceLabel(
  mustHaveRatio: number | undefined,
  supportingIds: readonly string[],
  requirements: ReadonlyMap<string, string>,
): string {
  const known = supportingIds.map(id => requirements.get(id));
  if (typeof mustHaveRatio === "number" && mustHaveRatio > 0 || known.includes("must_have")) {
    return "含必需条件 · 先核实证据";
  }
  if (known.length > 0 && known.every(value => value === "bonus")) return "加分项 · 可选补充";
  if (mustHaveRatio === 0) return "非必需 · 可择机准备";
  return "重要程度未确认 · 以岗位原文为准";
}

/** Requirement importance and personal evidence are separate; neither is a hiring verdict. */
export function gapNextStep(mustHaveRatio: number | undefined): string {
  if (typeof mustHaveRatio !== "number") return "先看岗位原文，再决定要核实、准备还是暂缓。";
  if (mustHaveRatio === 0) return "不必为了这一项推迟投递；有真实经历可补证据，没有可按需练习。";
  return "先问自己是否做过。做过就补可核实的经历；没做过就如实标为待准备，再决定是否投递。";
}

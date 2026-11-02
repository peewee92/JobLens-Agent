export type RankingOmission = {jobId: string; reason: "report_missing" | "report_stale" | "hard_conflict"; staleReasons: string[]};
export type RankingPreflight = {scope: string; ranked: string[]; candidates: string[]; insufficient: string[]; omissions: RankingOmission[]};

export function rankingScope(ids: readonly string[]): string {
  return JSON.stringify([...ids].sort());
}

const staleLabels: Record<string, string> = {
  retrieval_changed: "证据检索规则已更新，请保留历史结果并按当前事实更新匹配",
  policy_changed: "匹配规则已更新", profile_missing: "缺少当前职业资料", profile_changed: "职业资料已更新",
  search_intent_missing: "缺少当前求职意向", search_intent_changed: "求职意向已更新",
  requirements_missing: "缺少岗位要求", requirements_changed: "岗位要求已更新",
  requirements_not_released: "岗位要求的可用性检查未通过，请核对提取与审核记录",
  job_description_changed: "岗位描述已变化，需要重新分析岗位要求",
  job_user_marked_inactive: "你已标记此岗位失效；恢复标记后可重新检查",
  job_description_unavailable: "无法核实岗位描述或原分析依据，请检查后重新分析",
  job_missing: "岗位记录不可用", preference_inputs_changed: "岗位或偏好条件已变化",
};
export function staleReasonLabels(reasons: readonly string[]): string {
  return [...new Set(reasons.map(reason => staleLabels[reason] ?? "其他关联事实已变化"))].join("、");
}

/** Validate the response rather than silently treating malformed data as an empty ranking. */
export function rankingPreflight(ids: readonly string[], response: unknown): RankingPreflight {
  if (!ids.length || ids.length > 50 || new Set(ids).size !== ids.length) throw new Error("岗位选择无效，请重新选择。");
  if (!response || typeof response !== "object" || !Array.isArray((response as {items?: unknown}).items) || !Array.isArray((response as {omissions?: unknown}).omissions)) {
    throw new Error("排序检查返回的数据不完整，请稍后重试。");
  }
  const selected = new Set(ids);
  const ranked = new Set<string>();
  const candidates = new Set<string>();
  for (const item of (response as {items: unknown[]}).items) {
    const id = item && typeof item === "object" ? (item as {jobId?: unknown}).jobId : undefined;
    const candidate = item && typeof item === "object" ? (item as {targetCandidate?: unknown}).targetCandidate : undefined;
    if (typeof id !== "string" || !selected.has(id) || ranked.has(id) || typeof candidate !== "boolean") throw new Error("排序检查返回的数据不完整，请稍后重试。");
    ranked.add(id);
    if (candidate) candidates.add(id);
  }
  const omissions: RankingOmission[] = [];
  const seen = new Set(ranked);
  for (const raw of (response as {omissions: unknown[]}).omissions) {
    if (!raw || typeof raw !== "object") throw new Error("排序检查返回的数据不完整，请稍后重试。");
    const {jobId, reason, staleReasons} = raw as Record<string, unknown>;
    if (typeof jobId !== "string" || !selected.has(jobId) || seen.has(jobId) || !["report_missing", "report_stale", "hard_conflict"].includes(String(reason)) || !Array.isArray(staleReasons) || !staleReasons.every(x => typeof x === "string") || (reason === "report_stale" ? staleReasons.length === 0 : staleReasons.length !== 0)) throw new Error("排序检查返回的数据不完整，请稍后重试。");
    seen.add(jobId);
    omissions.push({jobId, reason: reason as RankingOmission["reason"], staleReasons});
  }
  if (seen.size !== ids.length) throw new Error("排序检查返回的数据不完整，请稍后重试。");
  return {scope: rankingScope(ids), ranked: ids.filter(id => ranked.has(id)), candidates: ids.filter(id => candidates.has(id)), insufficient: ids.filter(id => ranked.has(id) && !candidates.has(id)), omissions};
}

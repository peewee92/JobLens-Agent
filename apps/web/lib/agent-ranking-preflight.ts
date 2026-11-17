const recoveryMessages = {
  job_unavailable: "岗位当前不可用。请核对岗位记录；若标记为失效，可恢复后重新检查。",
  description_incomplete: "岗位描述信息不足。请打开岗位详情，补充完整原文或重新采集后再分析。",
  description_too_long: "岗位描述超过分析长度限制。可使用保留职责和任职要求的版本重新添加。",
  description_not_extractable: "当前岗位来源没有提供可用的完整描述。请从原招聘页面重新采集详情。",
  requirement_analysis_failed: "上次分析这份描述时没有保存岗位要求。请核对原文，确认后重新分析，或先跳过。",
  requirements_not_analyzed: "当前描述还没有可用的岗位要求。请先在岗位详情分析要求。",
  requirements_need_review: "已分析岗位要求，但目前还不能用于匹配。请到岗位详情核对要求与页面提示。",
};
type RecoveryCode = keyof typeof recoveryMessages;

export type RankingOmission = {jobId: string; reason: "report_missing" | "report_stale" | "hard_conflict"; staleReasons: string[]; recoveryCode?: RecoveryCode};
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

export function rankingOmissionMessage(item: RankingOmission): string {
  if (item.reason === "hard_conflict") return "当前匹配发现明确的硬性条件冲突。请查看岗位的匹配依据和原始要求。";
  if (item.reason === "report_stale") return `原匹配报告已过期：${staleReasonLabels(item.staleReasons)}；请核对后更新匹配。`;
  return item.recoveryCode ? recoveryMessages[item.recoveryCode]
    : "尚无匹配报告。请核对已确认的职业资料与求职偏好，再到岗位详情生成匹配报告。";
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
    const {jobId, reason, staleReasons, recoveryCode} = raw as Record<string, unknown>;
    if (typeof jobId !== "string" || !selected.has(jobId) || seen.has(jobId) || (reason !== "report_missing" && reason !== "report_stale" && reason !== "hard_conflict") || !Array.isArray(staleReasons) || !staleReasons.every(x => typeof x === "string") || (reason === "report_stale" ? staleReasons.length === 0 : staleReasons.length !== 0)) throw new Error("排序检查返回的数据不完整，请稍后重试。");
    seen.add(jobId);
    omissions.push({
      jobId, reason, staleReasons,
      ...(reason === "report_missing" && typeof recoveryCode === "string" && Object.hasOwn(recoveryMessages, recoveryCode)
        ? {recoveryCode: recoveryCode as RecoveryCode} : {}),
    });
  }
  if (seen.size !== ids.length) throw new Error("排序检查返回的数据不完整，请稍后重试。");
  return {scope: rankingScope(ids), ranked: ids.filter(id => ranked.has(id)), candidates: ids.filter(id => candidates.has(id)), insufficient: ids.filter(id => ranked.has(id) && !candidates.has(id)), omissions};
}

import type {MatchRecommendation} from "@/lib/contracts";

export function selectFeedbackDisplayItems<
  T extends {report: {reportId: string}},
>(
  items: readonly T[],
  nextPendingReportId: string | null,
  limit: number,
  pinnedReportIds: readonly string[] = [],
): T[] {
  const visible = items.slice(0, limit);
  const requiredIds = [nextPendingReportId, ...pinnedReportIds].filter(
    (reportId): reportId is string => Boolean(reportId),
  );

  for (const reportId of requiredIds) {
    if (visible.some((item) => item.report.reportId === reportId)) continue;
    const requiredItem = items.find((item) => item.report.reportId === reportId);
    if (requiredItem) visible.push(requiredItem);
  }

  return visible;
}

export const matchRecommendationLabels: Record<MatchRecommendation, string> = {
  strong: "值得优先投",
  good: "值得投",
  stretch: "可以尝试",
  low: "证据不足，当前不建议优先投入",
  blocked: "当前不建议投",
};

export const matchRecommendationDescriptions: Record<MatchRecommendation, string> = {
  strong: "核心要求和主要优先项都有明确经历支撑，可以作为优先投递目标。",
  good: "硬条件已经满足，整体值得投递，但仍有少量优先项需要补强。",
  stretch: "没有确认的硬性淘汰项，但仍有关键条件需要进一步确认，适合作为挑战岗位有选择地尝试。",
  low: "没有明确硬性冲突，但当前经历对岗位核心偏好支撑较弱，建议把时间优先留给更匹配的岗位。",
  blocked: "存在明确硬条件缺口；相关经历可以作为补强方向，但不能覆盖当前硬门槛。",
};

export const matchRecommendationClasses: Record<MatchRecommendation, string> = {
  strong: "match-recommendation-strong",
  good: "match-recommendation-good",
  stretch: "match-recommendation-stretch",
  low: "match-recommendation-low",
  blocked: "match-recommendation-blocked",
};


const reportStaleReasonLabels: Record<string, string> = {
  policy_changed: "匹配规则已更新，这份历史报告仍保留原规则结论",
  profile_missing: "当前没有已确认职业资料",
  profile_changed: "已确认职业资料已更新",
  search_intent_missing: "当前没有已确认求职意向",
  search_intent_changed: "求职意向已更新，或旧报告未绑定意向版本",
  requirements_missing: "当前没有可用的岗位要求提取",
  requirements_changed: "岗位要求已更新",
  job_missing: "原岗位已不可用",
  preference_inputs_changed: "岗位条件或求职偏好的分析输入已变化，或旧报告未记录输入指纹",
};

export function reportStaleReasonLabel(code: string): string {
  return reportStaleReasonLabels[code] ?? "分析输入已变化，请核实后更新分析";
}


export const recommendationGroups = {
  priority: {label: "优先投入", description: "核心证据支持，没有已确认硬冲突。优先比较这些岗位的投入价值。"},
  challenge: {label: "挑战／待核实", description: "有相关基础，仍有关键未知或差距。可以有选择地尝试，不代表所有条件已经满足。"},
  insufficient: {label: "证据不足", description: "目前不足以给出积极推荐；可查看要求、核实真实事实和准备方向，不会用来填满目标建议。"},
  blocked: {label: "暂不建议", description: "已确认事实或明确偏好与岗位硬条件冲突。可检查或更正事实，不能用学习承诺替代现有资格。"},
} as const;
export type RecommendationGroup = keyof typeof recommendationGroups;
export const recommendationGroupByType: Record<MatchRecommendation, RecommendationGroup> = {
  strong: "priority", good: "priority", stretch: "challenge", low: "insufficient", blocked: "blocked",
};

export function groupRecommendationItems<T extends {report: {recommendation: MatchRecommendation}}>(items: readonly T[]) {
  const groups: Record<RecommendationGroup, T[]> = {priority: [], challenge: [], insufficient: [], blocked: []};
  for (const item of items) groups[recommendationGroupByType[item.report.recommendation]].push(item);
  return groups;
}

export function selectDefaultTargetSuggestions<T extends {report: {recommendation: MatchRecommendation}}>(items: readonly T[]): T[] {
  return items.filter(({report}) => ["strong", "good", "stretch"].includes(report.recommendation)).slice(0, 3);
}

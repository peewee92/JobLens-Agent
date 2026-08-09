import type {MatchRecommendation} from "@/lib/contracts";

export const matchRecommendationLabels: Record<MatchRecommendation, string> = {
  strong: "值得优先投",
  good: "值得投",
  stretch: "可以尝试",
  low: "当前不建议优先投入",
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

import type {
  RequirementReviewBatchCase,
  RequirementReviewBatchSummary,
  RequirementReviewCandidate,
  RequirementReviewIssueCode,
} from "@/lib/contracts";

export const requirementReviewIssueLabels: Record<RequirementReviewIssueCode, string> = {
  missing_requirement: "遗漏要求",
  unsupported_requirement: "无依据要求",
  wrong_importance: "重要性错误",
  wrong_type: "类型错误",
  wrong_normalization: "能力归一化错误",
  evidence_mismatch: "证据片段不匹配",
  duplicate_requirement: "重复要求",
  other: "其他问题",
};

export function requirementReviewCohortKey(
  candidate: RequirementReviewCandidate,
): string {
  return [
    candidate.provider,
    candidate.model,
    candidate.extractorVersion,
    candidate.promptVersion,
  ].join("::");
}

export function canSelectRequirementCandidate(
  candidate: RequirementReviewCandidate,
  selected: RequirementReviewCandidate[],
): boolean {
  if (selected.some((item) => item.extractionId === candidate.extractionId)) {
    return true;
  }
  if (selected.length >= 20) return false;
  if (selected.length === 0) return true;
  return requirementReviewCohortKey(candidate) === requirementReviewCohortKey(selected[0]);
}

export function sortRequirementReviewCases(
  cases: RequirementReviewBatchCase[],
): RequirementReviewBatchCase[] {
  return [...cases].sort((left, right) => {
    if (left.review === null && right.review !== null) return -1;
    if (left.review !== null && right.review === null) return 1;
    if (left.isCurrent !== right.isCurrent) return left.isCurrent ? 1 : -1;
    return left.caseIndex - right.caseIndex;
  });
}

export function requirementReviewEvidenceLabel(
  summary: RequirementReviewBatchSummary,
): string {
  if (summary.formalEvidenceEligible) return "20 条正式人工质量证据";
  if (summary.staleCaseCount > 0) return `已过期：${summary.staleCaseCount} 条不是当前版本`;
  if (!summary.completed) return `进行中：${summary.reviewedCount}/${summary.sampleSize}`;
  if (summary.provider === "fixture") return "Fixture 练习证据";
  if (summary.sampleSize < 20) return `练习批次：${summary.sampleSize}/20`;
  return "尚不满足正式证据条件";
}

import type {
  RequirementEvalCaseResult,
  RequirementEvalRunSummary,
} from "@/lib/contracts";

export interface RequirementEvalReviewActions {
  canAccept: boolean;
  canReject: boolean;
  reason: string | null;
}

export function reviewActionsForRequirementRun(
  run: RequirementEvalRunSummary,
  alreadyReviewed: boolean,
): RequirementEvalReviewActions {
  if (alreadyReviewed) {
    return {
      canAccept: false,
      canReject: false,
      reason: "这次评测已有人工审核结论，不能重复提交。",
    };
  }
  if (run.mode !== "live") {
    return {
      canAccept: false,
      canReject: false,
      reason: "离线测试只检查流程是否正常，不能用于正式人工审核。",
    };
  }
  return {
    canAccept: run.gatePassed && run.releaseEligible,
    canReject: true,
    reason:
      run.gatePassed && run.releaseEligible
        ? null
        : "这次在线评测不符合通过条件，仍可以记录未通过的原因。",
  };
}

export function sortRequirementEvalCases(
  cases: RequirementEvalCaseResult[],
): RequirementEvalCaseResult[] {
  return [...cases].sort((left, right) => {
    if (left.passed !== right.passed) return left.passed ? 1 : -1;
    return left.caseId.localeCompare(right.caseId);
  });
}

export function formatRate(value: number | null): string {
  return value === null ? "—" : `${(value * 100).toFixed(1)}%`;
}

export function formatDelta(value: number | null): string {
  if (value === null) return "—";
  const prefix = value > 0 ? "+" : "";
  return `${prefix}${(value * 100).toFixed(1)}%`;
}

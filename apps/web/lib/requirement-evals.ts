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
      reason: "该运行已经有不可变审查记录。",
    };
  }
  if (run.mode !== "live") {
    return {
      canAccept: false,
      canReject: false,
      reason: "Fixture 运行只用于验证评测管线，不能进行正式人工审查。",
    };
  }
  return {
    canAccept: run.gatePassed && run.releaseEligible,
    canReject: true,
    reason:
      run.gatePassed && run.releaseEligible
        ? null
        : "该 live 运行未达到接受条件，但仍可记录 rejected 审查。",
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

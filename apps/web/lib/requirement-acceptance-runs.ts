import type {
  RequirementAcceptanceDatasetState,
  RequirementAcceptanceReadinessNextAction,
  RequirementAcceptanceRunCase,
  RequirementAcceptanceRunCaseStatus,
  RequirementAcceptanceRunStatus,
  RequirementAcceptanceRunSummary,
} from "@/lib/contracts";

export const requirementAcceptanceDatasetStateLabels: Record<
  RequirementAcceptanceDatasetState,
  string
> = {
  missing: "尚未导入正式数据集",
  selection_required: "存在多个正式数据集，需明确选择",
  invalid: "正式数据集无效",
  ready: "正式数据集已冻结",
};

export const requirementAcceptanceNextActionLabels: Record<
  RequirementAcceptanceReadinessNextAction,
  string
> = {
  fix_blockers: "先修复准备阻塞",
  run_canary: "可由 CLI 执行受控 Canary",
  review_canary: "需要你人工审核 Canary",
  resume_run: "可由 CLI 受控继续",
  open_manual_review: "需要完成 20 条人工验收",
  stopped: "已按人工决定停止",
};

export function requirementAcceptanceNextActionClass(
  action: RequirementAcceptanceReadinessNextAction,
): string {
  if (action === "review_canary" || action === "open_manual_review") {
    return "status-live";
  }
  if (action === "run_canary" || action === "resume_run") {
    return "status-pass";
  }
  if (action === "stopped") return "status-fail";
  return "status-fixture";
}

export const requirementAcceptanceRunStatusLabels: Record<
  RequirementAcceptanceRunStatus,
  string
> = {
  pending: "尚未执行",
  partial: "受控执行中",
  awaiting_canary_review: "等待 Canary 人工判断",
  stopped: "人工停止",
  ready: "已生成审核批次",
};

export const requirementAcceptanceCaseStatusLabels: Record<
  RequirementAcceptanceRunCaseStatus,
  string
> = {
  pending: "未处理",
  reused: "安全复用",
  extracted: "本 Run 抽取成功",
  failed: "调用失败",
  deferred: "本轮未调用",
};

export function requirementAcceptanceCaseStatusClass(
  status: RequirementAcceptanceRunCaseStatus,
): string {
  if (status === "extracted" || status === "reused") return "status-pass";
  if (status === "failed") return "status-fail";
  return "status-fixture";
}

export function requirementAcceptanceRunStatusClass(
  status: RequirementAcceptanceRunStatus,
): string {
  if (status === "ready") return "status-pass";
  if (status === "stopped") return "status-fail";
  if (status === "awaiting_canary_review") return "status-live";
  return "status-fixture";
}

export function sortRequirementAcceptanceRuns(
  runs: readonly RequirementAcceptanceRunSummary[],
): RequirementAcceptanceRunSummary[] {
  const priority: Record<RequirementAcceptanceRunStatus, number> = {
    awaiting_canary_review: 0,
    partial: 1,
    pending: 2,
    stopped: 3,
    ready: 4,
  };
  return [...runs].sort((left, right) => {
    const statusDelta = priority[left.status] - priority[right.status];
    if (statusDelta !== 0) return statusDelta;
    return Date.parse(right.updatedAt) - Date.parse(left.updatedAt);
  });
}

export function requirementAcceptanceCaseIsProviderOutage(
  runCase: RequirementAcceptanceRunCase,
): boolean {
  if (runCase.errorCode === "RequirementExtractorUnavailableError") return true;
  return /HTTPStatusError\(status=(429|503|504)(?:,|\))/.test(
    runCase.errorMessage ?? runCase.traceError ?? "",
  );
}

export type RequirementProviderOutageSummary = {
  outageCaseCount: number;
  caseIndexes: number[];
  statusCounts: Record<string, number>;
};

export function summarizeRequirementProviderOutages(
  cases: readonly RequirementAcceptanceRunCase[],
): RequirementProviderOutageSummary {
  const outageCases = cases.filter(requirementAcceptanceCaseIsProviderOutage);
  const statusCounts: Record<string, number> = {};
  for (const runCase of outageCases) {
    const message = `${runCase.errorMessage ?? ""} ${runCase.traceError ?? ""}`;
    const match = /HTTPStatusError\(status=(429|503|504)(?:,|\))/.exec(message);
    const status = match?.[1] ?? "unknown";
    statusCounts[status] = (statusCounts[status] ?? 0) + 1;
  }
  return {
    outageCaseCount: outageCases.length,
    caseIndexes: outageCases.map((runCase) => runCase.caseIndex).sort((a, b) => a - b),
    statusCounts,
  };
}

export function attemptedCanaryCases(
  cases: readonly RequirementAcceptanceRunCase[],
): RequirementAcceptanceRunCase[] {
  return [...cases]
    .filter((item) => item.isCanaryEvidence)
    .sort((left, right) => left.caseIndex - right.caseIndex);
}

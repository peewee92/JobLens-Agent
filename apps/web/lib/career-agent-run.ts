export class CareerAgentRunHttpError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "CareerAgentRunHttpError";
  }
}

const SAFE_FACT_ID = /^[A-Za-z0-9_-]{1,120}$/;

export function shouldForgetPendingThread(error: unknown): boolean {
  return error instanceof CareerAgentRunHttpError && error.status === 404;
}

export function buildGapHandoffHref(jobIds: readonly string[]): string | null {
  const safeJobIds = Array.from(new Set(jobIds.filter((jobId) => SAFE_FACT_ID.test(jobId)))).slice(0, 10);
  if (safeJobIds.length === 0) return null;

  const query = new URLSearchParams();
  for (const jobId of safeJobIds) query.append("jobId", jobId);
  query.set("from", "agent");
  return `/gaps?${query.toString()}`;
}


export function targetSelectionBlockMessage(currentStep: string): string | null {
  if (currentStep === "update_matching") return "本次小批处理已保存。请查看逐岗位进度，明确继续下一批或只分析已完成岗位；刷新不会继续。";
  if (currentStep === "update_inputs_changed") return "更新期间事实或报告已变化，保留已保存记录；请返回原范围重新预检。";
  if (currentStep === "target_evidence_insufficient") {
    return "当前只有证据不足的分析结果，无法提出可靠目标。请先核实资料或查看岗位要求。";
  }
  if (currentStep === "match_not_ready") {
    return "当前没有可进入目标建议的有效匹配报告。请先查看分类与原因，必要时生成或更新匹配结果。";
  }
  return null;
}

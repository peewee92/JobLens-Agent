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

/** User-facing explanation only; the server state remains authoritative. */
export function careerAgentStepSummary(step: string): string {
  const messages: Record<string, string> = {
    analysis_created: "分析请求已保存，尚需继续处理所选岗位。",
    rank_jobs: "岗位排序已保存，可继续准备目标岗位确认。",
    target_cohort_confirmation: "岗位排序已完成，等待你确认目标岗位。",
    target_cohort_resume: "目标岗位的决定已保存，可继续检查资料并准备分析。",
    skill_gap_ready: "目标岗位已确认，分析结果尚未保存；可以继续分析，不必重复确认。",
    skill_gap_completed: "能力差距分析已完成。",
    target_cohort_rejected: "你已拒绝本次目标建议，分析已结束。",
    continue_stale_career_context: "职业资料或求职意向已变化，请核对后重新分析。",
    resume_stale_match_reports: "目标确认期间，岗位或匹配依据已变化，本次分析已停止。请检查岗位和匹配报告后重新分析。",
    analysis_facts_changed: "分析期间资料、意向或岗位事实已变化；如有已保存材料，仅供历史查看。",
    update_inputs_changed: "更新期间事实或报告已变化，保留已保存记录；请返回原范围重新预检。",
    target_evidence_insufficient: "当前证据不足以提出目标建议，请先核对岗位要求和真实资料。",
    match_not_ready: "缺少可用的匹配报告，请先检查岗位及输入。",
    legacy_completed_no_snapshot: "旧运行没有保存完整结果，请重新分析。",
    legacy_reanalysis_required: "旧运行不能按当前规则继续，请重新分析。",
  };
  return Object.hasOwn(messages, step) ? messages[step] : "请查看当前运行状态；如分析尚未完成，可按页面提示继续或检查输入。";
}

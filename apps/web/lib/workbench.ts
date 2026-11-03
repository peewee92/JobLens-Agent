export type Workbench = {
  snapshot: {
    profileVersion: number | null; searchIntentVersion: number | null; evidenceCount: number;
    inputIssueCodes: string[]; jobCount: number;
    currentRun: {threadId: string; status: string; currentStep: string; jobCount: number; targetCount: number;
      executionTargetCount: number; resultId: string | null; resultIsCurrent: boolean | null; updatedAt: string; partial?: boolean; completedReportCount?: number} | null;
    workspaces: {workspaceId: string; jobId: string; title: string; status: string; openActionCount: number;
      currentAnalysisThreadId: string | null}[];
    changes: {kind: string; occurredAt: string; href: string}[];
  };
  nextAction: {code: string; label: string; reason: string; href: string};
};

export const runStatusLabels: Record<string, string> = {
  created: "尚未开始", running: "分析中", resuming: "继续处理中", interrupted: "等待确认目标",
  completed: "分析已完成", cancelled: "已取消", blocked: "需要修复输入", failed: "执行失败", stale: "事实已变化",
};
export const workspaceStatusLabels: Record<string, string> = {
  considering: "考虑中", preparing: "准备中", ready_to_apply: "待投递", applied: "已投递",
  interviewing: "面试中", offer: "已获录用意向", rejected: "未通过", withdrawn: "已退出",
};
export function inputIssueLabel(code: string): string {
  const labels: Record<string, string> = {
    profile_missing: "尚未确认职业资料", profile_headline_missing: "请确认职业方向说明",
    profile_evidence_missing: "请确认至少一项真实经历证据", profile_skills_missing: "请确认技能及其证据关联",
    profile_years_invalid: "工作年限需要核实，不能是负数",
    profile_evidence_invalid: "请补全经历的标识、摘要和来源",
    profile_evidence_keys_duplicated: "存在重复经历标识，请核对后重新确认",
    profile_skill_names_duplicated: "存在重复技能名称，请核对",
    profile_skill_evidence_missing: "部分技能尚未关联已确认经历",
    profile_skill_evidence_reference_invalid: "技能引用了当前资料中不存在的经历",
    search_intent_target_roles_duplicated: "目标岗位方向重复，请核对",
    search_intent_minimum_salary_invalid: "最低薪资需要核实，不能是负数",
    search_intent_missing: "尚未确认求职意向", search_intent_target_roles_missing: "请确认目标岗位方向",
  };
  return labels[code] ?? "有一项职业资料或意向需要核对，请打开资料页查看";
}
export function workbenchChangeLabel(kind: string): string {
  const labels: Record<string, string> = {
    analysis_partial: "保存了部分范围分析",
    profile_confirmed: "确认了职业资料", search_intent_confirmed: "确认了求职意向",
    workspace_created: "建立了求职工作区", resume_variant_saved: "保存了岗位简历事实草稿",
    resume_variant_reviewed: "人工审核了简历事实", action_completed: "完成了一项准备行动",
    status_changed: "人工更新了投递状态",
    application_status_updated: "人工更新了投递状态", application_status_changed: "人工更新了投递状态",
    evidence_proposed: "提交了待确认事实", evidence_confirmed: "确认了新增事实", rematch_completed: "更新了岗位匹配",
  };
  return labels[kind] ?? (kind.startsWith("analysis_") ? `分析状态：${runStatusLabels[kind.slice(9)] ?? "有变化"}` : "工作区有新记录");
}

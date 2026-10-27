import type {ApplicationExecutionAction} from "./contracts";

const statusOrder: Record<string, number> = {in_progress: 0, todo: 1, done: 2, skipped: 3};
const purposeOrder: Record<string, number> = {collect_evidence: 0, learn: 1, practice: 2, improve_resume: 3, prepare_interview: 4};
export const actionStatusLabels: Record<string, string> = {todo: "待开始", in_progress: "进行中", done: "已完成", skipped: "已跳过"};
export const actionPurposeLabels: Record<string, string> = {
  collect_evidence: "核实并补充真实证据", learn: "补充学习与实践", practice: "完成相关实践", improve_resume: "整理岗位简历事实", prepare_interview: "准备真实经历说明",
};

export function prioritizeApplicationActions(actions: readonly ApplicationExecutionAction[]): ApplicationExecutionAction[] {
  return [...actions].sort((a, b) => (statusOrder[a.status] ?? 4) - (statusOrder[b.status] ?? 4)
    || (purposeOrder[a.actionType] ?? 5) - (purposeOrder[b.actionType] ?? 5)
    || a.createdAt.localeCompare(b.createdAt) || a.actionId.localeCompare(b.actionId));
}

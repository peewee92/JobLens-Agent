import type {BatchMatchExecutionResponse} from "./contracts";

export type BatchMatchIssue = Pick<BatchMatchExecutionResponse["items"][number], "jobId" | "status" | "errorCode" | "blockerCodes">;

/** Only terminal problems, not work explicitly deferred to a later round. */
export function collectBatchIssues(previous: readonly BatchMatchIssue[], items: BatchMatchExecutionResponse["items"]): BatchMatchIssue[] {
  const byId = new Map(previous.map(item => [item.jobId, item]));
  for (const item of items) {
    if (item.status === "succeeded") byId.delete(item.jobId);
    else if (item.status === "failed" || item.status === "input_blocked" || item.status === "persistence_blocked") byId.set(item.jobId, item);
  }
  return [...byId.values()];
}

export function batchIssueDescription(issue: BatchMatchIssue): string {
  if (issue.blockerCodes.includes("job_user_marked_inactive")) return "你已标记此岗位失效；可在岗位详情中恢复后重新分析";
  if (issue.blockerCodes.includes("job_availability_changed")) return "分析期间岗位状态发生变化；请检查岗位后重新分析";
  if (issue.errorCode === "semantic_model_authorization_required") return "需要在线语义判断；当前未授权调用模型";
  if (issue.status === "input_blocked") return "资料或岗位要求尚未准备好，请核对输入";
  if (issue.status === "persistence_blocked") return "匹配结果暂时无法保存，请检查服务和数据库";
  return "本次匹配未完成，请查看岗位详情并核对后再试";
}

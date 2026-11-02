"use client";

import {useRouter} from "next/navigation";
import {useState} from "react";

import type {ApiErrorBody, BatchMatchExecutionResponse} from "@/lib/contracts";
import {userFacingApiError} from "@/lib/user-facing-errors";
import {collectBatchIssues, type BatchMatchIssue} from "@/lib/batch-match-issues";
import {BatchMatchIssues} from "@/components/batch-match-issues";
import {BatchMatchSuccesses} from "@/components/batch-match-successes";
import {BatchMatchUncertainNotice} from "@/components/batch-match-uncertain-notice";
import {importMatchButtonLabel, isUncertainMatchResponse, mergeImportMatchRemainder, splitImportMatchBatch} from "@/lib/import-match-batching";

type RunState =
  | {kind: "idle"; message: string}
  | {kind: "running"; message: string}
  | {kind: "success"; message: string}
  | {kind: "uncertain"; message: string}
  | {kind: "error"; message: string};

async function responseMessage(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as Partial<ApiErrorBody>;
    return userFacingApiError(body, `匹配失败（${response.status}），请稍后重试。`);
  } catch {
    return `匹配失败（${response.status}），请稍后重试。`;
  }
}

export function ImportBatchMatch({jobIds, importId}: {jobIds: string[]; importId: string}) {
  const router = useRouter();
  const [pendingJobIds, setPendingJobIds] = useState(() => Array.from(new Set(jobIds)));
  const [issues, setIssues] = useState<BatchMatchIssue[]>([]);
  const [previousFailures, setPreviousFailures] = useState(0);
  const [previousAuthorizationBlock, setPreviousAuthorizationBlock] = useState(false);
  const [succeededJobIds, setSucceededJobIds] = useState<string[]>([]);
  const [state, setState] = useState<RunState>({kind: "idle", message: ""});

  async function run() {
    if (pendingJobIds.length === 0 || state.kind === "running" || state.kind === "uncertain") return;

    setState({
      kind: "running",
      message: `正在匹配 ${Math.min(pendingJobIds.length, 5)} 个已准备岗位…`,
    });

    const {requestJobIds, untouchedJobIds} = splitImportMatchBatch(pendingJobIds);
    try {
      const response = await fetch("/api/match-batch", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({jobIds: requestJobIds, maxReadyJobs: 5}),
      });
      if (!response.ok) {
        if (isUncertainMatchResponse(response.status)) {
          setState({kind: "uncertain", message: ""});
          return;
        }
        setState({kind: "error", message: await responseMessage(response)});
        return;
      }

      const result = (await response.json()) as BatchMatchExecutionResponse;
      setIssues(previous => collectBatchIssues(previous, result.items));
      const failures = result.failedCount + result.inputBlockedCount + result.persistenceBlockedCount;
      const authorizationBlocked = result.items.some(item => item.errorCode === "semantic_model_authorization_required");
      const totalFailures = previousFailures + failures;
      const anyAuthorizationBlock = previousAuthorizationBlock || authorizationBlocked;
      setPreviousFailures(totalFailures);
      setPreviousAuthorizationBlock(anyAuthorizationBlock);
      const newlySucceededJobIds = result.items
        .filter((item) => item.status === "succeeded")
        .map((item) => item.jobId);
      const allSucceededJobIds = Array.from(new Set([...succeededJobIds, ...newlySucceededJobIds]));
      setSucceededJobIds(allSucceededJobIds);

      const nextPendingJobIds = mergeImportMatchRemainder(result.resumeJobIds, untouchedJobIds);
      if (nextPendingJobIds.length > 0) {
        setPendingJobIds(nextPendingJobIds);
        setState({
          kind: totalFailures > 0 ? "error" : "success",
          message: `本轮完成 ${result.succeededCount} 个${totalFailures ? `，累计 ${totalFailures} 个未完成` : ""}；还有 ${nextPendingJobIds.length} 个可由你继续匹配。${anyAuthorizationBlock ? "部分岗位需要在线语义判断，当前未调用真实模型；请查看岗位详情。" : ""}`,
        });
        if (totalFailures === 0) router.refresh();
        return;
      }

      setPendingJobIds([]);
      setState({
        kind: totalFailures > 0 ? "error" : "success",
        message:
          totalFailures > 0
            ? `本轮完成 ${result.succeededCount} 个，累计 ${totalFailures} 个未完成。${anyAuthorizationBlock ? "部分岗位需要在线语义判断，当前未调用真实模型；请查看岗位详情。" : "请查看岗位状态后再决定是否继续。"}`
            : `已完成 ${result.succeededCount} 个岗位的匹配，当前批次结果已更新。`,
      });
      if (allSucceededJobIds.length > 0 && allSucceededJobIds.length <= 20 && totalFailures === 0) {
        router.replace(`/imports/${encodeURIComponent(importId)}?afterMatchJobs=${encodeURIComponent(allSucceededJobIds.join(","))}#batch-match-result`);
      } else if (allSucceededJobIds.length === 0 && totalFailures === 0) {
        router.refresh();
      }
    } catch {
      setState({kind: "uncertain", message: ""});
    }
  }

  if (jobIds.length === 0) return null;

  const buttonLabel = importMatchButtonLabel(pendingJobIds.length,
    succeededJobIds.length > 0 || previousFailures > 0, state.kind === "running");

  return (
    <div className="notice">
      <strong>{state.kind === "uncertain" ? "请先核对本轮结果" : pendingJobIds.length > 0 ? "这批岗位已可以进入匹配" : "本轮匹配已结束"}</strong>
      {pendingJobIds.length > 0 && state.kind !== "uncertain" && <p>
        只会处理当前输入事实已准备好的岗位，每次检查最多 50 个、每轮最多匹配 5 个；超出范围的岗位会保留供后续手动继续。只有你点击后才会执行；需要在线语义判断的岗位会等待逐次授权能力，不会调用真实模型。
      </p>}
      {pendingJobIds.length > 0 && state.kind !== "uncertain" && <div className="actions">
        <button
          className="button"
          type="button"
          onClick={run}
          disabled={state.kind === "running" || pendingJobIds.length === 0}
        >
          {buttonLabel}
        </button>
      </div>}
      {state.kind === "uncertain" && <BatchMatchUncertainNotice />}
      <BatchMatchSuccesses jobIds={succeededJobIds} />
      <BatchMatchIssues issues={issues} />
      {state.message ? (
        <p className={state.kind === "error" ? "inline-error" : "muted"} role="status" aria-live="polite">
          {state.message}
        </p>
      ) : null}
    </div>
  );
}

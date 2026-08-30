"use client";

import {useRouter} from "next/navigation";
import {useState} from "react";

import type {ApiErrorBody, BatchMatchExecutionResponse} from "@/lib/contracts";
import {userFacingApiError} from "@/lib/user-facing-errors";

type RunState =
  | {kind: "idle"; message: string}
  | {kind: "running"; message: string}
  | {kind: "success"; message: string}
  | {kind: "error"; message: string};

async function responseMessage(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as Partial<ApiErrorBody>;
    return userFacingApiError(body, `匹配失败（${response.status}），请稍后重试。`);
  } catch {
    return `匹配失败（${response.status}），请稍后重试。`;
  }
}

export function ImportBatchMatch({jobIds}: {jobIds: string[]}) {
  const router = useRouter();
  const [pendingJobIds, setPendingJobIds] = useState(jobIds);
  const [state, setState] = useState<RunState>({kind: "idle", message: ""});

  async function run() {
    if (pendingJobIds.length === 0 || state.kind === "running") return;

    setState({
      kind: "running",
      message: `正在匹配 ${Math.min(pendingJobIds.length, 10)} 个已准备岗位…`,
    });

    try {
      const response = await fetch("/api/match-batch", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({jobIds: pendingJobIds, maxReadyJobs: 10}),
      });
      if (!response.ok) {
        setState({kind: "error", message: await responseMessage(response)});
        return;
      }

      const result = (await response.json()) as BatchMatchExecutionResponse;
      const failures = result.failedCount + result.inputBlockedCount + result.persistenceBlockedCount;

      if (result.resumeJobIds.length > 0) {
        setPendingJobIds(result.resumeJobIds);
        setState({
          kind: failures > 0 ? "error" : "success",
          message: `本轮完成 ${result.succeededCount} 个；还有 ${result.resumeJobIds.length} 个可由你继续匹配。`,
        });
        router.refresh();
        return;
      }

      setPendingJobIds([]);
      setState({
        kind: failures > 0 ? "error" : "success",
        message:
          failures > 0
            ? `本轮完成 ${result.succeededCount} 个，另有 ${failures} 个未完成。请查看岗位状态后再决定是否继续。`
            : `已完成 ${result.succeededCount} 个岗位的匹配，当前批次结果已更新。`,
      });
      router.refresh();
    } catch {
      setState({kind: "error", message: "匹配失败，请检查本地 JobLens 服务后重试。"});
    }
  }

  if (jobIds.length === 0) return null;

  const buttonLabel = state.kind === "running"
    ? "正在匹配…"
    : pendingJobIds.length < jobIds.length && pendingJobIds.length > 0
      ? `继续匹配剩余 ${pendingJobIds.length} 个`
      : `匹配这批已准备岗位（${Math.min(pendingJobIds.length, 10)} 个）`;

  return (
    <div className="notice">
      <strong>这批岗位已可以进入匹配</strong>
      <p>
        只会处理当前输入事实已准备好的岗位，每轮最多 10 个。只有你点击后才会执行；如果某些 Requirement 需要语义判断，过程中可能调用已配置的模型。
      </p>
      <div className="actions">
        <button
          className="button"
          type="button"
          onClick={run}
          disabled={state.kind === "running" || pendingJobIds.length === 0}
        >
          {buttonLabel}
        </button>
      </div>
      {state.message ? (
        <p className={state.kind === "error" ? "inline-error" : "muted"} role="status" aria-live="polite">
          {state.message}
        </p>
      ) : null}
    </div>
  );
}

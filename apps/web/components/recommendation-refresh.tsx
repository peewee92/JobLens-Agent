"use client";

import {useRouter} from "next/navigation";
import {useState} from "react";

import type {ApiErrorBody, BatchMatchExecutionResponse} from "@/lib/contracts";
import {userFacingApiError} from "@/lib/user-facing-errors";

type RefreshState =
  | {kind: "idle"; message: string}
  | {kind: "running"; message: string}
  | {kind: "success"; message: string}
  | {kind: "error"; message: string};

async function responseMessage(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as Partial<ApiErrorBody>;
    return userFacingApiError(body, `重新计算失败（${response.status}），请稍后重试。`);
  } catch {
    return `重新计算失败（${response.status}），请稍后重试。`;
  }
}

export function RecommendationRefresh({jobIds}: {jobIds: string[]}) {
  const router = useRouter();
  const [pendingJobIds, setPendingJobIds] = useState(jobIds);
  const [state, setState] = useState<RefreshState>({kind: "idle", message: ""});

  async function run() {
    if (pendingJobIds.length === 0 || state.kind === "running") return;
    setState({
      kind: "running",
      message: `正在重新计算 ${Math.min(pendingJobIds.length, 10)} 个岗位…`,
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
          kind: "success",
          message: `已完成 ${result.succeededCount} 个；还有 ${result.resumeJobIds.length} 个可继续重新计算。`,
        });
        router.refresh();
        return;
      }

      setPendingJobIds([]);
      setState({
        kind: failures > 0 ? "error" : "success",
        message:
          failures > 0
            ? `本轮完成 ${result.succeededCount} 个，另有 ${failures} 个未完成。可以查看岗位详情确认阻塞原因。`
            : `已重新计算 ${result.succeededCount} 个岗位，优先级已更新。`,
      });
      router.refresh();
    } catch {
      setState({kind: "error", message: "重新计算失败，请检查本地服务后重试。"});
    }
  }

  if (jobIds.length === 0) {
    return (
      <div className="notice">
        <strong>当前没有可安全重新计算的岗位</strong>
        <p>先补齐职业背景或等待岗位要求进入可信版本；系统不会为了凑结果绕过输入门禁。</p>
      </div>
    );
  }

  return (
    <div className="notice">
      <strong>资料更新后，重新计算岗位</strong>
      <p>
        当前有 {jobIds.length} 个岗位的输入事实已准备好。重新计算只会使用你确认过的 Profile 和当前可信岗位要求；如果某些条件需要语义判断，才可能调用模型。
      </p>
      <div className="actions">
        <button className="button" type="button" onClick={run} disabled={state.kind === "running" || pendingJobIds.length === 0}>
          {state.kind === "running"
            ? "正在重新计算…"
            : pendingJobIds.length < jobIds.length && pendingJobIds.length > 0
              ? `继续计算剩余 ${pendingJobIds.length} 个`
              : `重新计算 ${Math.min(pendingJobIds.length, 10)} 个岗位`}
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

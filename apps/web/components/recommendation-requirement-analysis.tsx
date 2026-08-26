"use client";

import {useRouter} from "next/navigation";
import {useState} from "react";

import type {ApiErrorBody, RequirementBatchExecutionResponse} from "@/lib/contracts";
import {userFacingApiError} from "@/lib/user-facing-errors";

type State =
  | {kind: "idle"; message: string}
  | {kind: "running"; message: string}
  | {kind: "success"; message: string}
  | {kind: "error"; message: string};

async function responseMessage(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as Partial<ApiErrorBody>;
    return userFacingApiError(body, `岗位要求分析失败（${response.status}），请稍后重试。`);
  } catch {
    return `岗位要求分析失败（${response.status}），请稍后重试。`;
  }
}

export function RecommendationRequirementAnalysis({jobIds}: {jobIds: string[]}) {
  const router = useRouter();
  const [state, setState] = useState<State>({kind: "idle", message: ""});
  const [providerBlocked, setProviderBlocked] = useState(false);

  async function run() {
    if (jobIds.length === 0 || state.kind === "running" || providerBlocked) return;
    setState({
      kind: "running",
      message: `正在分析 ${jobIds.length} 个优先岗位的要求…`,
    });

    try {
      const response = await fetch("/api/requirement-batch", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({jobIds, maxReadyJobs: 5}),
      });
      if (!response.ok) {
        setState({kind: "error", message: await responseMessage(response)});
        return;
      }

      const result = (await response.json()) as RequirementBatchExecutionResponse;
      if (result.providerUnavailableCount > 0) {
        setProviderBlocked(true);
        setState({
          kind: "error",
          message: `Provider 当前不可用，本轮已立即停止。成功 ${result.succeededCount} 个，剩余 ${result.deferredCount} 个未继续调用。为避免连续产生失败调用，本页将暂停再次分析；确认 Provider 恢复后再刷新页面重试。`,
        });
        router.refresh();
        return;
      }

      const incomplete = result.failedCount + result.notSelectedCount + result.deferredCount;
      setState({
        kind: incomplete > 0 ? "error" : "success",
        message:
          incomplete > 0
            ? `本轮成功 ${result.succeededCount} 个，另有 ${incomplete} 个未完成；页面已按最新 Coverage 重新排序。`
            : `已完成 ${result.succeededCount} 个岗位要求分析，正在更新可比较岗位范围。`,
      });
      router.refresh();
    } catch {
      setState({kind: "error", message: "岗位要求分析失败，请检查本地服务后重试。"});
    }
  }

  if (jobIds.length === 0) return null;

  return (
    <div className="notice">
      <strong>可以直接分析这一批优先岗位</strong>
      <p>
        本轮最多分析 {jobIds.length} 个由 Backend Coverage Planner 选出的岗位。该操作可能调用模型；如果 Provider 出现 429/503/504 等不可用情况，Backend 会立即停止后续岗位，不会继续批量消耗调用。
      </p>
      <div className="actions">
        <button className="button" type="button" onClick={run} disabled={state.kind === "running" || providerBlocked}>
          {state.kind === "running"
            ? "正在分析岗位要求…"
            : providerBlocked
              ? "Provider 暂不可用"
              : `分析下一批 ${jobIds.length} 个岗位`}
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

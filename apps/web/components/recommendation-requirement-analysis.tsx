"use client";

import {useRouter} from "next/navigation";
import Link from "next/link";
import {useState} from "react";

import type {ApiErrorBody, RequirementBatchExecutionResponse} from "@/lib/contracts";
import {userFacingApiError} from "@/lib/user-facing-errors";
import {isUncertainMatchResponse} from "@/lib/import-match-batching";
import {BatchMatchUncertainNotice} from "@/components/batch-match-uncertain-notice";

type State =
  | {kind: "idle"; message: string}
  | {kind: "running"; message: string}
  | {kind: "success"; message: string}
  | {kind: "uncertain"; message: string}
  | {kind: "error"; message: string; availabilityIssues?: {jobId: string; errorCode: string}[]};

const PROVIDER_COOLDOWN_STORAGE_KEY = "joblens:requirement-provider-cooldown-until";
const PROVIDER_COOLDOWN_MS = 30 * 60 * 1000;

function providerCooldownActive(): boolean {
  if (typeof window === "undefined") return false;
  const stored = window.sessionStorage.getItem(PROVIDER_COOLDOWN_STORAGE_KEY);
  if (!stored) return false;
  const cooldownUntil = Number(stored);
  if (!Number.isFinite(cooldownUntil) || cooldownUntil <= Date.now()) {
    window.sessionStorage.removeItem(PROVIDER_COOLDOWN_STORAGE_KEY);
    return false;
  }
  return true;
}

function startProviderCooldown(): void {
  if (typeof window === "undefined") return;
  window.sessionStorage.setItem(
    PROVIDER_COOLDOWN_STORAGE_KEY,
    String(Date.now() + PROVIDER_COOLDOWN_MS),
  );
}

function clearProviderCooldown(): void {
  if (typeof window === "undefined") return;
  window.sessionStorage.removeItem(PROVIDER_COOLDOWN_STORAGE_KEY);
}

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
  const [providerBlocked, setProviderBlocked] = useState(providerCooldownActive);
  const [liveCostConfirmed, setLiveCostConfirmed] = useState(false);

  async function run() {
    if (
      jobIds.length === 0
      || state.kind === "running"
      || state.kind === "uncertain"
      || providerBlocked
      || !liveCostConfirmed
    ) return;
    setState({
      kind: "running",
      message: `正在分析 ${jobIds.length} 个优先岗位的要求…`,
    });

    try {
      const response = await fetch("/api/requirement-batch", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({jobIds, maxReadyJobs: 5, confirmLiveCost: true}),
      });
      if (!response.ok) {
        setLiveCostConfirmed(false);
        if (isUncertainMatchResponse(response.status)) {
          setState({kind: "uncertain", message: ""});
          return;
        }
        setState({kind: "error", message: await responseMessage(response)});
        return;
      }

      const result = (await response.json()) as RequirementBatchExecutionResponse;
      if (result.items.some(item => item.errorCode === "requirement_model_authorization_required")) {
        clearProviderCooldown();
        setProviderBlocked(false);
        setLiveCostConfirmed(false);
        setState({kind: "error", message: "本入口尚不支持逐次授权和费用记录，未调用真实模型；请使用已有岗位要求或离线数据。"});
        router.refresh();
        return;
      }
      if (result.providerUnavailableCount > 0) {
        startProviderCooldown();
        setProviderBlocked(true);
        setLiveCostConfirmed(false);
        setState({
          kind: "error",
          message: `Provider 当前不可用，本轮已立即停止。成功 ${result.succeededCount} 个，剩余 ${result.deferredCount} 个未继续调用。为避免刷新页面后立即重复产生失败付费调用，本浏览器会话将冷却 30 分钟后再允许重试。`,
        });
        router.refresh();
        return;
      }

      clearProviderCooldown();
      setLiveCostConfirmed(false);
      const incomplete = result.failedCount + result.notSelectedCount + result.deferredCount;
      const availabilityIssues = result.items.filter(item => item.errorCode === "job_user_marked_inactive" || item.errorCode === "job_availability_changed" || item.errorCode === "job_description_changed_during_extraction" || item.errorCode === "requirement_extraction_superseded").map(item => ({jobId: item.jobId, errorCode: item.errorCode!}));
      setState({
        kind: incomplete > 0 ? "error" : "success",
        ...(incomplete > 0 ? {availabilityIssues} : {}),
        message:
          incomplete > 0
            ? `本轮成功 ${result.succeededCount} 个，另有 ${incomplete} 个未完成；页面已按最新 Coverage 重新排序。`
            : `已完成 ${result.succeededCount} 个岗位要求分析，正在更新可比较岗位范围。`,
      });
      router.refresh();
    } catch {
      setLiveCostConfirmed(false);
      setState({kind: "uncertain", message: ""});
    }
  }

  if (jobIds.length === 0) return null;

  return (
    <div className="notice">
      <strong>{state.kind === "uncertain" ? "请先核对本轮结果" : "可以直接分析这一批优先岗位"}</strong>
      <p>
        本轮最多分析 {jobIds.length} 个选出的岗位。目前仅离线替身可执行；真实模型入口在逐次授权和费用记录接入前受阻。
      </p>
      {state.kind !== "uncertain" && <label className="feedback-reason-option">
        <input
          type="checkbox"
          checked={liveCostConfirmed}
          onChange={(event) => setLiveCostConfirmed(event.target.checked)}
          disabled={state.kind === "running" || providerBlocked}
        />
        我确认本轮最多分析 {jobIds.length} 个岗位，并了解目前只支持离线执行；本次确认只对这一轮有效。
      </label>}
      {state.kind !== "uncertain" && <div className="actions">
        <button
          className="button"
          type="button"
          onClick={run}
          disabled={state.kind === "running" || providerBlocked || !liveCostConfirmed}
        >
          {state.kind === "running"
            ? "正在分析岗位要求…"
            : providerBlocked
              ? "Provider 暂不可用"
              : `分析下一批 ${jobIds.length} 个岗位`}
        </button>
      </div>}
      {state.kind === "uncertain" && <BatchMatchUncertainNotice kind="requirements" />}
      {state.kind === "error" && state.availabilityIssues?.length ? <ul>
        {state.availabilityIssues.map(item => <li key={item.jobId}>
          <Link href={`/jobs/${encodeURIComponent(item.jobId)}`}>查看岗位 {item.jobId}</Link>：{userFacingApiError({error: {code: item.errorCode, message: ""}}, "请检查岗位状态") }
        </li>)}
      </ul> : null}
      {state.message ? (
        <p className={state.kind === "error" ? "inline-error" : "muted"} role="status" aria-live="polite">
          {state.message}
        </p>
      ) : null}
    </div>
  );
}

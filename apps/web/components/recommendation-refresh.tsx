"use client";

import {useRouter} from "next/navigation";
import {useState} from "react";

import type {ApiErrorBody, BatchMatchExecutionResponse} from "@/lib/contracts";
import {userFacingApiError} from "@/lib/user-facing-errors";
import {collectBatchIssues, type BatchMatchIssue} from "@/lib/batch-match-issues";
import {BatchMatchIssues} from "@/components/batch-match-issues";

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

export function RecommendationRefresh({
  jobIds,
  focusJobId = null,
  focusJobTitle = null,
  focusReportId = null,
  returnHref = null,
  returnLabel = "回到这批岗位看改善结果",
}: {
  jobIds: string[];
  focusJobId?: string | null;
  focusJobTitle?: string | null;
  focusReportId?: string | null;
  returnHref?: string | null;
  returnLabel?: string;
}) {
  const router = useRouter();
  const [pendingJobIds, setPendingJobIds] = useState(jobIds);
  const [issues, setIssues] = useState<BatchMatchIssue[]>([]);
  const [previousFailures, setPreviousFailures] = useState(0);
  const [previousAuthorizationBlock, setPreviousAuthorizationBlock] = useState(false);
  const [state, setState] = useState<RefreshState>({kind: "idle", message: ""});
  const isFocused = Boolean(focusJobId);

  // MatchReport snapshots are immutable. Wait until the refreshed server tree
  // exposes a new report id before scrolling, instead of racing router.refresh().
  function refreshAndScroll() {
    router.refresh();
    if (!focusJobId) return;

    let framesRemaining = 120;
    const scrollWhenFresh = () => {
      const el = document.getElementById(`focus-job-${focusJobId}`);
      const renderedReportId = el?.dataset.reportId ?? null;
      const refreshedReportIsVisible = Boolean(el) && (
        focusReportId === null || renderedReportId !== focusReportId
      );

      if (refreshedReportIsVisible) {
        el?.scrollIntoView({behavior: "smooth", block: "center"});
        return;
      }
      if (framesRemaining <= 0) return;

      framesRemaining -= 1;
      requestAnimationFrame(scrollWhenFresh);
    };

    requestAnimationFrame(scrollWhenFresh);
  }

  async function run() {
    if (pendingJobIds.length === 0 || state.kind === "running") return;
    setState({
      kind: "running",
      message: `正在重新计算 ${Math.min(pendingJobIds.length, 5)} 个岗位…`,
    });

    try {
      const response = await fetch("/api/match-batch", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({jobIds: pendingJobIds, maxReadyJobs: 5}),
      });
      if (!response.ok) {
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
      if (result.resumeJobIds.length > 0) {
        setPendingJobIds(result.resumeJobIds);
        setState({
          kind: totalFailures > 0 ? "error" : "success",
          message: `已完成 ${result.succeededCount} 个${totalFailures ? `，累计 ${totalFailures} 个未完成` : ""}；还有 ${result.resumeJobIds.length} 个可继续重新计算。${anyAuthorizationBlock ? "其中有岗位需要语义判断；本入口尚不支持逐次授权，未调用真实模型；请查看岗位详情。" : ""}`,
        });
        if (totalFailures === 0) refreshAndScroll();
        return;
      }

      setPendingJobIds([]);
      setState({
        kind: totalFailures > 0 ? "error" : "success",
        message:
          totalFailures > 0
            ? `本轮完成 ${result.succeededCount} 个，累计 ${totalFailures} 个未完成。${anyAuthorizationBlock ? "部分岗位需要语义判断；本入口尚不支持逐次授权，未调用真实模型；请查看岗位详情。" : "可以查看岗位详情确认阻塞原因。"}`
            : isFocused
              ? `已优先重算你刚补充证据的岗位，优先级已更新。`
              : `已重新计算 ${result.succeededCount} 个岗位，优先级已更新。`,
      });
      if (totalFailures === 0) refreshAndScroll();
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

  const buttonLabel = state.kind === "running"
    ? "正在重新计算…"
    : pendingJobIds.length < jobIds.length && pendingJobIds.length > 0
      ? `继续计算剩余 ${pendingJobIds.length} 个`
      : isFocused
        ? `优先重算这个岗位${pendingJobIds.length > 1 ? `及另外 ${Math.min(pendingJobIds.length - 1, 4)} 个` : ""}`
        : `重新计算 ${Math.min(pendingJobIds.length, 5)} 个岗位`;

  return (
    <div className="notice">
      <strong>{isFocused ? "针对你刚补充的岗位，优先重算" : "资料更新后，重新计算岗位"}</strong>
      <p>
        {isFocused
          ? `你刚为${focusJobTitle ? `「${focusJobTitle}」` : "这个岗位"}补充了证据。重新计算会先重算它，再看其余已准备好的岗位；只会使用你确认过的 Profile 和当前可信岗位要求。`
          : `当前有 ${jobIds.length} 个岗位的输入事实已准备好。重新计算只会使用你确认过的 Profile 和当前可信岗位要求；需要在线语义判断的岗位会等待逐次授权能力，不会调用真实模型。`}
      </p>
      <div className="actions">
        <button className="button" type="button" onClick={run} disabled={state.kind === "running" || pendingJobIds.length === 0}>
          {buttonLabel}
        </button>
      </div>
      <BatchMatchIssues issues={issues} />
      {state.message ? (
        <p className={state.kind === "error" ? "inline-error" : "muted"} role="status" aria-live="polite">
          {state.message}
        </p>
      ) : null}
      {returnHref && state.kind === "success" && pendingJobIds.length === 0 ? (
        <div className="actions">
          <button className="button-secondary" type="button" onClick={() => router.push(returnHref)}>
            {returnLabel}
          </button>
        </div>
      ) : null}
    </div>
  );
}

"use client";

import {useRouter} from "next/navigation";
import {useEffect, useRef, useState, type FormEvent} from "react";

import type {RequirementCallPlan} from "@/lib/contracts";
import {requirementExtractionOutcome} from "@/lib/requirement-extraction-outcome";
import {shortJobDescriptionGuidance} from "@/lib/job-requirements";
import {AuthorizedRequirementExtraction} from "@/components/authorized-requirement-extraction";
import {BatchMatchUncertainNotice} from "@/components/batch-match-uncertain-notice";

export function JobRequirementExtractButton({
  jobId,
  disabled,
  disabledReason,
  hasExisting,
  returnTo,
  actionLabel,
  localProduct = false,
}: {
  jobId: string;
  disabled: boolean;
  disabledReason?: string;
  hasExisting: boolean;
  returnTo?: string;
  actionLabel?: string;
  localProduct?: boolean;
}) {
  const router = useRouter();
  const [planLoaded, setPlanLoaded] = useState(false);
  const [plan, setPlan] = useState<RequirementCallPlan | null>(null);
  useEffect(() => {
    let active = true;
    fetch(`/api/jobs/${encodeURIComponent(jobId)}/requirement-call-plan`)
      .then(async response => response.ok ? response.json() as Promise<RequirementCallPlan> : null)
      .then(value => { if (active) setPlan(value); })
      .catch(() => { /* Legacy offline endpoint stays zero-budget when this query fails. */ })
      .finally(() => { if (active) setPlanLoaded(true); });
    return () => { active = false; };
  }, [jobId]);
  const [status, setStatus] = useState<"idle" | "submitting" | "error" | "uncertain">("idle");
  const [message, setMessage] = useState("");
  const [confirmLiveCost, setConfirmLiveCost] = useState(false);
  const requestLocked = useRef(false);

  async function extract(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    if (disabled || requestLocked.current) return;
    if (!confirmLiveCost) {
      setStatus("error");
      setMessage("请先确认本次离线岗位要求分析。");
      return;
    }
    requestLocked.current = true;
    setStatus("submitting");
    setMessage("");
    try {
      const response = await fetch(
        `/api/jobs/${encodeURIComponent(jobId)}/requirement-extractions`,
        {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({confirmLiveCost: true}),
        },
      );
      const outcome = requirementExtractionOutcome(response.status, await response.json().catch(() => null), jobId);
      if (outcome.kind === "uncertain") {
        setStatus("uncertain");
        return;
      }
      setConfirmLiveCost(false);
      if (outcome.kind === "rejected") {
        setStatus("error");
        setMessage(outcome.message);
      } else {
        setStatus("idle");
        router.refresh();
      }
      requestLocked.current = false;
    } catch {
      setStatus("uncertain");
    }
  }

  if (disabled) return <p className="notice">{disabledReason ?? shortJobDescriptionGuidance}</p>;
  if (!planLoaded) return <p role="status">正在核对可用分析方式…</p>;
  if (plan && (plan.available || plan.latestRequest)) return <AuthorizedRequirementExtraction key={`${jobId}:${plan.planDigest}`} jobId={jobId} plan={plan} disabled={disabled} />;
  if (localProduct) return <p className="notice">当前还不能使用岗位分析模型。请检查已指定的模型配置与完整岗位原文，再刷新查看；没有发送模型请求，也不会用离线样本替代。</p>;

  const fallbackReturnTo = returnTo ?? `/jobs/${jobId}`;
  const fallbackAction = `/api/jobs/${encodeURIComponent(jobId)}/requirement-extractions?returnTo=${encodeURIComponent(fallbackReturnTo)}`;

  return (
    <div>
      <form action={fallbackAction} method="post" onSubmit={extract}>
        <label className="requirement-live-cost-consent">
          <input
            checked={confirmLiveCost}
            disabled={disabled || status === "submitting" || status === "uncertain"}
            name="confirmLiveCost"
            onChange={(event) => setConfirmLiveCost(event.target.checked)}
            required
            type="checkbox"
            value="true"
          />{" "}
          我确认执行离线岗位要求分析；此入口不调用真实模型。
        </label>
        <button
          className="button requirement-action-button"
          disabled={disabled || status === "submitting" || status === "uncertain" || !confirmLiveCost}
          type="submit"
        >
          {status === "submitting"
            ? "正在分析…"
            : status === "error" ? "重试岗位要求分析"
            : actionLabel ?? (hasExisting
              ? "重新分析岗位要求"
              : "分析岗位要求")}
        </button>
      </form>
      {status === "uncertain" ? <BatchMatchUncertainNotice kind="requirements" /> : null}
      {status === "submitting" ? (
        <div
          aria-live="polite"
          className="requirement-processing-indicator"
          role="status"
        >
          <span aria-hidden="true" className="loading-spinner" />
          <div>
            <strong>正在分析岗位要求…</strong>
            <p>这可能需要一点时间，请保持页面打开。</p>
          </div>
        </div>
      ) : null}
      {disabled ? (
        <p className="notice">{disabledReason ?? shortJobDescriptionGuidance}</p>
      ) : null}
      {status === "error" ? <p className="inline-error" role="alert">{message}</p> : null}
    </div>
  );
}

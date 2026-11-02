"use client";

import {useRouter} from "next/navigation";
import {useEffect, useState, type FormEvent} from "react";

import type {ApiErrorBody, JobRequirementExtraction, RequirementCallPlan} from "@/lib/contracts";
import {userFacingApiError} from "@/lib/user-facing-errors";
import {shortJobDescriptionGuidance} from "@/lib/job-requirements";
import {isUncertainMatchResponse} from "@/lib/import-match-batching";
import {AuthorizedRequirementExtraction} from "@/components/authorized-requirement-extraction";
import {BatchMatchUncertainNotice} from "@/components/batch-match-uncertain-notice";

export function JobRequirementExtractButton({
  jobId,
  disabled,
  disabledReason,
  hasExisting,
  returnTo,
  actionLabel,
}: {
  jobId: string;
  disabled: boolean;
  disabledReason?: string;
  hasExisting: boolean;
  returnTo?: string;
  actionLabel?: string;
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

  async function extract(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    if (status === "submitting" || status === "uncertain") return;
    setStatus("submitting");
    setMessage("");
    if (!confirmLiveCost) {
      setStatus("error");
      setMessage("请先确认本次离线岗位要求分析。");
      return;
    }
    try {
      const response = await fetch(
        `/api/jobs/${encodeURIComponent(jobId)}/requirement-extractions`,
        {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({confirmLiveCost: true}),
        },
      );
      if (isUncertainMatchResponse(response.status)) {
        setStatus("uncertain");
        return;
      }
      const body = (await response.json()) as
        | JobRequirementExtraction
        | ApiErrorBody;
      if (!response.ok) {
        setStatus("error");
        setMessage(userFacingApiError(
            "error" in body ? body : null,
            `岗位要求分析失败（${response.status}），请稍后重试。`,
          ));
        return;
      }
      router.refresh();
      setConfirmLiveCost(false);
      setStatus("idle");
    } catch {
      setStatus("uncertain");
    }
  }

  if (!planLoaded) return <p role="status">正在核对可用分析方式…</p>;
  if (plan && (plan.available || plan.latestRequest)) return <AuthorizedRequirementExtraction key={`${jobId}:${plan.planDigest}`} jobId={jobId} plan={plan} disabled={disabled} />;

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
            onChange={(event) => {
              setConfirmLiveCost(event.target.checked);
              setMessage("");
              if (status === "error") setStatus("idle");
            }}
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
      {status === "error" ? <p className="inline-error">{message}</p> : null}
    </div>
  );
}

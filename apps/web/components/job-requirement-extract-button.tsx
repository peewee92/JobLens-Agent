"use client";

import {useRouter} from "next/navigation";
import {useState, type FormEvent} from "react";

import type {ApiErrorBody, JobRequirementExtraction} from "@/lib/contracts";
import {userFacingApiError} from "@/lib/user-facing-errors";

export function JobRequirementExtractButton({
  jobId,
  disabled,
  hasExisting,
}: {
  jobId: string;
  disabled: boolean;
  hasExisting: boolean;
}) {
  const router = useRouter();
  const [status, setStatus] = useState<"idle" | "submitting" | "error">("idle");
  const [message, setMessage] = useState("");
  const [confirmLiveCost, setConfirmLiveCost] = useState(false);

  async function extract(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    setStatus("submitting");
    setMessage("");
    if (!confirmLiveCost) {
      setStatus("error");
      setMessage("请先确认本次岗位要求分析可能产生真实 Provider 成本。");
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
      const body = (await response.json()) as
        | JobRequirementExtraction
        | ApiErrorBody;
      if (!response.ok) {
        throw new Error(
          userFacingApiError(
            "error" in body ? body : null,
            `岗位要求分析失败（${response.status}），请稍后重试。`,
          ),
        );
      }
      router.refresh();
      setConfirmLiveCost(false);
      setStatus("idle");
    } catch (caught) {
      setStatus("error");
      setMessage(caught instanceof Error ? caught.message : "分析岗位要求时发生未知错误。");
    }
  }

  const fallbackAction = `/api/jobs/${encodeURIComponent(jobId)}/requirement-extractions?returnTo=${encodeURIComponent(`/jobs/${jobId}`)}`;

  return (
    <div>
      <form action={fallbackAction} method="post" onSubmit={extract}>
        <label className="requirement-live-cost-consent">
          <input
            checked={confirmLiveCost}
            disabled={disabled || status === "submitting"}
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
          我确认这次岗位要求分析可能调用真实 Provider 并产生费用。
        </label>
        <button
          className="button requirement-action-button"
          disabled={disabled || status === "submitting" || !confirmLiveCost}
          type="submit"
        >
          {status === "submitting"
            ? "Analyzing…"
            : hasExisting
              ? "重新分析岗位要求"
              : "分析岗位要求"}
        </button>
      </form>
      {status === "submitting" ? (
        <div
          aria-live="polite"
          className="requirement-processing-indicator"
          role="status"
        >
          <span aria-hidden="true" className="loading-spinner" />
          <div>
            <strong>Analyzing job requirements…</strong>
            <p>This can take a moment. Please keep this page open.</p>
          </div>
        </div>
      ) : null}
      {disabled ? (
        <p className="notice">当前岗位缺少足够的 JD 文本，暂时无法分析岗位要求。</p>
      ) : null}
      {status === "error" ? <p className="inline-error">{message}</p> : null}
    </div>
  );
}

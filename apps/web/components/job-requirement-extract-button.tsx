"use client";

import {useRouter} from "next/navigation";
import {useState} from "react";

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

  async function extract() {
    setStatus("submitting");
    setMessage("");
    try {
      const response = await fetch(
        `/api/jobs/${encodeURIComponent(jobId)}/requirement-extractions`,
        {method: "POST"},
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
      setStatus("idle");
    } catch (caught) {
      setStatus("error");
      setMessage(caught instanceof Error ? caught.message : "分析岗位要求时发生未知错误。");
    }
  }

  return (
    <div>
      <button
        className="button requirement-action-button"
        disabled={disabled || status === "submitting"}
        onClick={extract}
        type="button"
      >
        {status === "submitting"
          ? "正在分析…"
          : hasExisting
            ? "重新分析岗位要求"
            : "分析岗位要求"}
      </button>
      {disabled ? (
        <p className="notice">当前岗位缺少足够的 JD 文本，暂时无法分析岗位要求。</p>
      ) : null}
      {status === "error" ? <p className="inline-error">{message}</p> : null}
    </div>
  );
}

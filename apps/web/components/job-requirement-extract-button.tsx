"use client";

import {useRouter} from "next/navigation";
import {useState} from "react";

import type {ApiErrorBody, JobRequirementExtraction} from "@/lib/contracts";

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
          "error" in body ? body.error.message : `抽取失败（${response.status}）`,
        );
      }
      router.refresh();
      setStatus("idle");
    } catch (caught) {
      setStatus("error");
      setMessage(caught instanceof Error ? caught.message : "抽取岗位要求时发生未知错误。");
    }
  }

  return (
    <div>
      <button
        className="button-secondary"
        disabled={disabled || status === "submitting"}
        onClick={extract}
        type="button"
      >
        {status === "submitting"
          ? "正在抽取…"
          : hasExisting
            ? "重新抽取新版本"
            : "抽取结构化岗位要求"}
      </button>
      {disabled ? (
        <p className="notice">当前岗位没有足够的 JD 文本，无法抽取。</p>
      ) : null}
      {status === "error" ? <p className="inline-error">{message}</p> : null}
    </div>
  );
}

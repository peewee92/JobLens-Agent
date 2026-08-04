"use client";

import {useRouter} from "next/navigation";
import {useState} from "react";

import type {
  ApiErrorBody,
  RequirementReviewBatchFinalDecisionValue,
} from "@/lib/contracts";

export function RequirementReviewFinalDecisionForm({
  batchId,
  reviewer,
}: {
  batchId: string;
  reviewer: string;
}) {
  const router = useRouter();
  const [notes, setNotes] = useState("");
  const [pending, setPending] =
    useState<RequirementReviewBatchFinalDecisionValue | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit(decision: RequirementReviewBatchFinalDecisionValue) {
    setError(null);
    if (notes.trim().length < 20) {
      setError("请写至少 20 个字符的批次级人工质量结论。" );
      return;
    }
    setPending(decision);
    try {
      const response = await fetch(
        `/api/requirement-review-batches/${encodeURIComponent(batchId)}/final-decision`,
        {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({decision, reviewer, notes}),
        },
      );
      if (!response.ok) {
        const body = (await response.json()) as Partial<ApiErrorBody>;
        throw new Error(
          body.error?.message ?? `提交最终质量结论失败（${response.status}）。`,
        );
      }
      router.refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "提交最终质量结论失败。" );
    } finally {
      setPending(null);
    }
  }

  return (
    <div className="review-form">
      <p className="notice">
        这里不自动计算通过阈值。请基于 20 条逐 Case 判断、问题分布和 Trace，亲自决定该模型 cohort 是否可作为 Match 的 Requirement 事实基线。提交后不可修改。
      </p>
      <label>
        批次级人工结论
        <textarea
          value={notes}
          onChange={(event) => setNotes(event.target.value)}
          minLength={20}
          rows={6}
          required
          placeholder="说明为什么该批次可以或不可以进入 Match；至少 20 个字符。"
        />
      </label>
      <p className="muted">Reviewer：{reviewer}</p>
      {error ? <div className="inline-error">{error}</div> : null}
      <div className="actions">
        <button
          className="button"
          type="button"
          disabled={pending !== null}
          onClick={() => void submit("accept_for_match")}
        >
          {pending === "accept_for_match"
            ? "提交中…"
            : "Accept：允许该证据进入 Match"}
        </button>
        <button
          className="button-ghost"
          type="button"
          disabled={pending !== null}
          onClick={() => void submit("reject_for_match")}
        >
          {pending === "reject_for_match"
            ? "提交中…"
            : "Reject：禁止该证据进入 Match"}
        </button>
      </div>
    </div>
  );
}

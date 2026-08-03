"use client";

import {useRouter} from "next/navigation";
import {useMemo, useState} from "react";

import type {
  ApiErrorBody,
  RequirementEvalReviewDecision,
  RequirementEvalRunSummary,
} from "@/lib/contracts";
import {reviewActionsForRequirementRun} from "@/lib/requirement-evals";

export function RequirementEvalReviewForm({
  run,
  alreadyReviewed,
}: {
  run: RequirementEvalRunSummary;
  alreadyReviewed: boolean;
}) {
  const router = useRouter();
  const actions = useMemo(
    () => reviewActionsForRequirementRun(run, alreadyReviewed),
    [run, alreadyReviewed],
  );
  const [reviewer, setReviewer] = useState("local-user");
  const [notes, setNotes] = useState("");
  const [pending, setPending] = useState<RequirementEvalReviewDecision | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit(decision: RequirementEvalReviewDecision) {
    setError(null);
    setPending(decision);
    try {
      const response = await fetch(
        `/api/requirement-evals/${encodeURIComponent(run.id)}/review`,
        {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({decision, reviewer, notes}),
        },
      );
      if (!response.ok) {
        const body = (await response.json()) as Partial<ApiErrorBody>;
        throw new Error(body.error?.message ?? `审查提交失败（${response.status}）。`);
      }
      router.refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "审查提交失败。");
    } finally {
      setPending(null);
    }
  }

  if (!actions.canAccept && !actions.canReject) {
    return <p className="notice">{actions.reason}</p>;
  }

  return (
    <div className="review-form">
      <label>
        审查人
        <input
          value={reviewer}
          onChange={(event) => setReviewer(event.target.value)}
          required
        />
      </label>
      <label>
        审查说明
        <textarea
          value={notes}
          onChange={(event) => setNotes(event.target.value)}
          minLength={10}
          required
          placeholder="记录逐案例、importance 与 Trace 审查结论，至少 10 个字符。"
          rows={5}
        />
      </label>
      {actions.reason ? <p className="notice">{actions.reason}</p> : null}
      {error ? <div className="inline-error">{error}</div> : null}
      <div className="actions">
        <button
          className="button"
          type="button"
          disabled={!actions.canAccept || pending !== null}
          onClick={() => void submit("accepted")}
        >
          {pending === "accepted" ? "提交中…" : "接受并设为正式 baseline"}
        </button>
        <button
          className="button-ghost"
          type="button"
          disabled={!actions.canReject || pending !== null}
          onClick={() => void submit("rejected")}
        >
          {pending === "rejected" ? "提交中…" : "记录为 rejected"}
        </button>
      </div>
    </div>
  );
}

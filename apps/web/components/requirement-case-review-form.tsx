"use client";

import {useRouter} from "next/navigation";
import {useState} from "react";

import type {
  ApiErrorBody,
  RequirementReviewDecision,
  RequirementReviewIssueCode,
} from "@/lib/contracts";
import {requirementReviewIssueLabels} from "@/lib/requirement-reviews";

const issueCodes = Object.keys(requirementReviewIssueLabels) as RequirementReviewIssueCode[];

export function RequirementCaseReviewForm({
  batchId,
  caseId,
}: {
  batchId: string;
  caseId: string;
}) {
  const router = useRouter();
  const [selectedIssues, setSelectedIssues] = useState<RequirementReviewIssueCode[]>([]);
  const [notes, setNotes] = useState("");
  const [pending, setPending] = useState<RequirementReviewDecision | null>(null);
  const [error, setError] = useState<string | null>(null);

  function toggleIssue(issue: RequirementReviewIssueCode) {
    setSelectedIssues((current) =>
      current.includes(issue)
        ? current.filter((item) => item !== issue)
        : [...current, issue],
    );
  }

  async function submit(decision: RequirementReviewDecision) {
    setError(null);
    if (notes.trim().length < 10) {
      setError("请写至少 10 个字符的人工判断依据。" );
      return;
    }
    if (decision === "rejected" && selectedIssues.length === 0) {
      setError("Reject 至少选择一个问题类型。" );
      return;
    }
    setPending(decision);
    try {
      const response = await fetch(
        `/api/requirement-review-batches/${encodeURIComponent(batchId)}/cases/${encodeURIComponent(caseId)}/review`,
        {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({
            decision,
            issueCodes: decision === "accepted" ? [] : selectedIssues,
            notes,
          }),
        },
      );
      if (!response.ok) {
        const body = (await response.json()) as Partial<ApiErrorBody>;
        throw new Error(body.error?.message ?? `提交判断失败（${response.status}）。`);
      }
      router.refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "提交人工判断失败。" );
    } finally {
      setPending(null);
    }
  }

  return (
    <div className="review-form">
      <fieldset>
        <legend>发现的问题（仅 Reject 时提交）</legend>
        <div className="review-issue-grid">
          {issueCodes.map((issue) => (
            <label className="review-issue-option" key={issue}>
              <span>{requirementReviewIssueLabels[issue]}</span>
              <input
                type="checkbox"
                checked={selectedIssues.includes(issue)}
                disabled={pending !== null}
                onChange={() => toggleIssue(issue)}
              />
            </label>
          ))}
        </div>
      </fieldset>
      <label>
        人工判断依据
        <textarea
          value={notes}
          onChange={(event) => setNotes(event.target.value)}
          minLength={10}
          rows={4}
          required
          placeholder="比较完整 JD、抽取结果、importance、normalizedCapability 和 evidenceSpan 后写下结论。"
        />
      </label>
      {error ? <div className="inline-error">{error}</div> : null}
      <div className="actions">
        <button
          className="button"
          type="button"
          disabled={pending !== null}
          onClick={() => void submit("accepted")}
        >
          {pending === "accepted" ? "提交中…" : "Accept：本 Case 可接受"}
        </button>
        <button
          className="button-ghost"
          type="button"
          disabled={pending !== null}
          onClick={() => void submit("rejected")}
        >
          {pending === "rejected" ? "提交中…" : "Reject：记录质量问题"}
        </button>
      </div>
    </div>
  );
}

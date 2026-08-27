"use client";

import {useRouter} from "next/navigation";
import {useState} from "react";

import type {ApiErrorBody, FeedbackDecision, FeedbackReason} from "@/lib/contracts";
import {userFacingApiError} from "@/lib/user-facing-errors";

const decisionLabels: Record<FeedbackDecision, string> = {
  interested: "感兴趣",
  maybe: "再看看",
  rejected: "不考虑",
};

const rejectionReasonLabels: Record<FeedbackReason, string> = {
  role_fit: "方向不合适",
  skill_gap: "能力差距太大",
  compensation: "薪资不合适",
  location: "地点不合适",
  seniority: "职级不合适",
  company: "公司不合适",
  work_mode: "工作方式不合适",
  other: "其他",
};

export function RecommendationFeedback({
  matchReportId,
  jobId,
  initialDecision,
  initialReasons,
  initialNote,
}: {
  matchReportId: string;
  jobId: string;
  initialDecision: FeedbackDecision | null;
  initialReasons: FeedbackReason[];
  initialNote: string | null;
}) {
  const router = useRouter();
  const [savedDecision, setSavedDecision] = useState<FeedbackDecision | null>(initialDecision);
  const [savedReasons, setSavedReasons] = useState<FeedbackReason[]>(initialReasons);
  const [savedNote, setSavedNote] = useState<string | null>(initialNote);
  const [pendingDecision, setPendingDecision] = useState<FeedbackDecision | null>(null);
  const [rejectionReason, setRejectionReason] = useState<FeedbackReason>(
    initialReasons[0] ?? "role_fit",
  );
  const [otherNote, setOtherNote] = useState(initialReasons.includes("other") ? initialNote ?? "" : "");
  const [error, setError] = useState<string | null>(null);

  function isSameFeedback(
    decision: FeedbackDecision,
    reasons: FeedbackReason[] = [],
    note: string | null = null,
  ) {
    return savedDecision === decision
      && savedReasons.length === reasons.length
      && savedReasons.every((reason, index) => reason === reasons[index])
      && (savedNote ?? null) === (note ?? null);
  }

  async function submit(
    decision: FeedbackDecision,
    reasons: FeedbackReason[] = [],
    note: string | null = null,
  ) {
    if (isSameFeedback(decision, reasons, note)) return;
    setPendingDecision(decision);
    setError(null);
    try {
      const response = await fetch("/api/user-feedback", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          matchReportId,
          jobId,
          decision,
          reasons,
          note,
        }),
      });
      if (!response.ok) {
        let body: Partial<ApiErrorBody> | null = null;
        try {
          body = (await response.json()) as Partial<ApiErrorBody>;
        } catch {
          body = null;
        }
        setError(userFacingApiError(body, "反馈暂时保存失败，请稍后再试。"));
        if (body?.error?.code === "feedback_match_report_stale") {
          router.refresh();
        }
        return;
      }
      setSavedDecision(decision);
      setSavedReasons(reasons);
      setSavedNote(note);
      router.refresh();
    } catch {
      setError("反馈暂时保存失败，请稍后再试。");
    } finally {
      setPendingDecision(null);
    }
  }

  return (
    <div className="recommendation-feedback" aria-label="岗位反馈">
      <p className="muted">
        {savedDecision
          ? `你当前的选择：${decisionLabels[savedDecision]}${savedReasons.length > 0 ? ` · 原因：${savedReasons.map((reason) => rejectionReasonLabels[reason]).join("、")}` : ""}${savedNote ? ` · 补充：${savedNote}` : ""}`
          : "这条推荐符合你的真实判断吗？"}
      </p>
      <div className="actions">
        <button
          className="button-secondary"
          type="button"
          aria-pressed={savedDecision === "interested"}
          disabled={pendingDecision !== null || isSameFeedback("interested")}
          onClick={() => void submit("interested")}
        >
          {pendingDecision === "interested" ? "保存中…" : "感兴趣"}
        </button>
        <button
          className="button-ghost"
          type="button"
          aria-pressed={savedDecision === "maybe"}
          disabled={pendingDecision !== null || isSameFeedback("maybe")}
          onClick={() => void submit("maybe")}
        >
          {pendingDecision === "maybe" ? "保存中…" : "再看看"}
        </button>
        <select
          aria-label="不考虑原因"
          value={rejectionReason}
          onChange={(event) => setRejectionReason(event.target.value as FeedbackReason)}
          disabled={pendingDecision !== null}
        >
          {Object.entries(rejectionReasonLabels).map(([reason, label]) => (
            <option key={reason} value={reason}>{label}</option>
          ))}
        </select>
        {rejectionReason === "other" ? (
          <input
            aria-label="其他不考虑原因"
            type="text"
            value={otherNote}
            onChange={(event) => setOtherNote(event.target.value)}
            placeholder="补充你的真实原因"
            disabled={pendingDecision !== null}
          />
        ) : null}
        <button
          className="button-ghost"
          type="button"
          aria-pressed={
            savedDecision === "rejected"
            && isSameFeedback(
              "rejected",
              [rejectionReason],
              rejectionReason === "other" ? otherNote.trim() || null : null,
            )
          }
          disabled={
            pendingDecision !== null
            || (rejectionReason === "other" && otherNote.trim() === "")
            || isSameFeedback(
              "rejected",
              [rejectionReason],
              rejectionReason === "other" ? otherNote.trim() || null : null,
            )
          }
          onClick={() => void submit(
            "rejected",
            [rejectionReason],
            rejectionReason === "other" ? otherNote.trim() || null : null,
          )}
        >
          {pendingDecision === "rejected" ? "保存中…" : "不考虑"}
        </button>
      </div>
      {error ? <p className="error-text" role="alert">{error}</p> : null}
    </div>
  );
}

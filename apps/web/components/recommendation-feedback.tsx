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

const rejectionReasonOrder = Object.keys(rejectionReasonLabels) as FeedbackReason[];

function normalizeReasons(reasons: FeedbackReason[]) {
  return rejectionReasonOrder.filter((reason) => reasons.includes(reason));
}

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
  const [savedReasons, setSavedReasons] = useState<FeedbackReason[]>(normalizeReasons(initialReasons));
  const [savedNote, setSavedNote] = useState<string | null>(initialNote);
  const [pendingDecision, setPendingDecision] = useState<FeedbackDecision | null>(null);
  const [selectedReasons, setSelectedReasons] = useState<FeedbackReason[]>(normalizeReasons(initialReasons));
  const [otherNote, setOtherNote] = useState(initialReasons.includes("other") ? initialNote ?? "" : "");
  const [error, setError] = useState<string | null>(null);

  function isSameFeedback(
    decision: FeedbackDecision,
    reasons: FeedbackReason[] = [],
    note: string | null = null,
  ) {
    const normalizedReasons = normalizeReasons(reasons);
    return savedDecision === decision
      && savedReasons.length === normalizedReasons.length
      && savedReasons.every((reason, index) => reason === normalizedReasons[index])
      && (savedNote ?? null) === (note ?? null);
  }

  function toggleReason(reason: FeedbackReason) {
    setSelectedReasons((current) => normalizeReasons(
      current.includes(reason)
        ? current.filter((item) => item !== reason)
        : [...current, reason],
    ));
  }

  async function submit(
    decision: FeedbackDecision,
    reasons: FeedbackReason[] = [],
    note: string | null = null,
  ) {
    const normalizedReasons = normalizeReasons(reasons);
    if (isSameFeedback(decision, normalizedReasons, note)) return;
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
          reasons: normalizedReasons,
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
      setSavedReasons(normalizedReasons);
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
      </div>
      <fieldset disabled={pendingDecision !== null}>
        <legend>不考虑原因（可多选）</legend>
        <div className="actions">
          {Object.entries(rejectionReasonLabels).map(([reason, label]) => {
            const typedReason = reason as FeedbackReason;
            return (
              <label key={reason}>
                <input
                  type="checkbox"
                  checked={selectedReasons.includes(typedReason)}
                  onChange={() => toggleReason(typedReason)}
                />{" "}
                {label}
              </label>
            );
          })}
        </div>
        {selectedReasons.includes("other") ? (
          <input
            aria-label="其他不考虑原因"
            type="text"
            value={otherNote}
            onChange={(event) => setOtherNote(event.target.value)}
            placeholder="补充你的真实原因"
            disabled={pendingDecision !== null}
          />
        ) : null}
        <div className="actions">
          <button
            className="button-ghost"
            type="button"
            aria-pressed={
              savedDecision === "rejected"
              && isSameFeedback(
                "rejected",
                selectedReasons,
                selectedReasons.includes("other") ? otherNote.trim() || null : null,
              )
            }
            disabled={
              pendingDecision !== null
              || selectedReasons.length === 0
              || (selectedReasons.includes("other") && otherNote.trim() === "")
              || isSameFeedback(
                "rejected",
                selectedReasons,
                selectedReasons.includes("other") ? otherNote.trim() || null : null,
              )
            }
            onClick={() => void submit(
              "rejected",
              selectedReasons,
              selectedReasons.includes("other") ? otherNote.trim() || null : null,
            )}
          >
            {pendingDecision === "rejected" ? "保存中…" : "不考虑"}
          </button>
        </div>
      </fieldset>
      {error ? <p className="error-text" role="alert">{error}</p> : null}
    </div>
  );
}

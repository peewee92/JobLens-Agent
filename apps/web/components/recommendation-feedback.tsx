"use client";

import {useState} from "react";

import type {FeedbackDecision, FeedbackReason} from "@/lib/contracts";

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
}: {
  matchReportId: string;
  jobId: string;
  initialDecision: FeedbackDecision | null;
}) {
  const [savedDecision, setSavedDecision] = useState<FeedbackDecision | null>(initialDecision);
  const [pendingDecision, setPendingDecision] = useState<FeedbackDecision | null>(null);
  const [rejectionReason, setRejectionReason] = useState<FeedbackReason>("role_fit");
  const [error, setError] = useState<string | null>(null);

  async function submit(decision: FeedbackDecision, reasons: FeedbackReason[] = []) {
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
        }),
      });
      if (!response.ok) {
        throw new Error("feedback_save_failed");
      }
      setSavedDecision(decision);
    } catch {
      setError("反馈暂时保存失败，请稍后再试。");
    } finally {
      setPendingDecision(null);
    }
  }

  return (
    <div className="recommendation-feedback" aria-label="岗位反馈">
      <p className="muted">
        {savedDecision ? `你当前的选择：${decisionLabels[savedDecision]}` : "这条推荐符合你的真实判断吗？"}
      </p>
      <div className="actions">
        <button
          className="button-secondary"
          type="button"
          disabled={pendingDecision !== null}
          onClick={() => void submit("interested")}
        >
          {pendingDecision === "interested" ? "保存中…" : "感兴趣"}
        </button>
        <button
          className="button-ghost"
          type="button"
          disabled={pendingDecision !== null}
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
          {Object.entries(rejectionReasonLabels)
            .filter(([reason]) => reason !== "other")
            .map(([reason, label]) => (
              <option key={reason} value={reason}>{label}</option>
            ))}
        </select>
        <button
          className="button-ghost"
          type="button"
          disabled={pendingDecision !== null}
          onClick={() => void submit("rejected", [rejectionReason])}
        >
          {pendingDecision === "rejected" ? "保存中…" : "不考虑"}
        </button>
      </div>
      {error ? <p className="error-text" role="alert">{error}</p> : null}
    </div>
  );
}

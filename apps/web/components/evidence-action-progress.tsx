"use client";

import {useEffect, useState} from "react";

import {
  EVIDENCE_ACTION_STORAGE_KEY,
  evidenceActionStageLabel,
  parseEvidenceActionState,
  transitionEvidenceActionState,
  type EvidenceActionSnapshot,
  type EvidenceActionStage,
} from "@/lib/evidence-action-state";

interface EvidenceActionProgressProps {
  requirementId?: string | null;
  jobId?: string | null;
  capability?: string | null;
  requirementText?: string | null;
  stage?: EvidenceActionStage | null;
  compact?: boolean;
  completeCurrent?: boolean;
  successor?: Omit<EvidenceActionSnapshot, "stage" | "updatedAt"> | null;
}

export function EvidenceActionProgress({
  requirementId = null,
  jobId = null,
  capability = null,
  requirementText = null,
  stage = null,
  compact = false,
  completeCurrent = false,
  successor = null,
}: EvidenceActionProgressProps) {
  const [snapshot, setSnapshot] = useState<EvidenceActionSnapshot | null>(null);
  const [recentCompleted, setRecentCompleted] = useState<EvidenceActionSnapshot[]>([]);

  useEffect(() => {
    const stored = parseEvidenceActionState(window.localStorage.getItem(EVIDENCE_ACTION_STORAGE_KEY));
    const now = Date.now();
    const explicitCurrent = requirementId && stage
      ? {requirementId, jobId, capability, requirementText, stage, updatedAt: now}
      : null;
    const successorCurrent = successor
      ? {...successor, stage: "pending" as const, updatedAt: now}
      : null;
    const nextState = explicitCurrent || completeCurrent
      ? transitionEvidenceActionState(stored, completeCurrent ? successorCurrent : explicitCurrent, completeCurrent)
      : stored;

    if (!nextState) {
      window.localStorage.removeItem(EVIDENCE_ACTION_STORAGE_KEY);
      setSnapshot(null);
      setRecentCompleted([]);
      return;
    }
    window.localStorage.setItem(EVIDENCE_ACTION_STORAGE_KEY, JSON.stringify(nextState));
    setSnapshot(nextState.current);
    setRecentCompleted(nextState.recentCompleted);
  }, [requirementId, jobId, capability, requirementText, stage, completeCurrent, successor]);

  if (!snapshot && recentCompleted.length === 0) return null;

  return (
    <section className={compact ? "notice" : "detail-card"} data-testid="evidence-action-progress">
      {snapshot ? (
        <>
          <div className="section-heading-row">
            <div>
              <p className="eyebrow">当前 Evidence 行动</p>
              <h2>{snapshot.capability ?? "核实一条真实岗位要求"}</h2>
            </div>
            <span className="status-pill">{evidenceActionStageLabel(snapshot.stage)}</span>
          </div>
          {snapshot.requirementText ? <p>岗位要求：{snapshot.requirementText}</p> : null}
          <p className="muted">
            {snapshot.stage === "pending"
              ? "先只核实你真实做过的内容；没有证据就保留缺口。这个行动会保存在当前浏览器，离开页面后回来仍可看到。"
              : snapshot.stage === "evidence_saved"
                ? "真实资料已经保存，但当前还缺少可比较的前后 MatchReport，因此暂不判断是否改善。"
                : "这项核实已经完成 Re-match 对照；具体改善与剩余缺口以当前匹配结果为准。"}
          </p>
        </>
      ) : null}
      {recentCompleted[0] ? (
        <div className="muted" data-testid="evidence-action-completed">
          最近完成：{recentCompleted[0].capability ?? recentCompleted[0].requirementText ?? "一条 Evidence 核实"} · {evidenceActionStageLabel("completed")}
        </div>
      ) : null}
    </section>
  );
}

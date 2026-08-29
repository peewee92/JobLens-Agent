"use client";

import {useEffect, useState} from "react";

import {
  EVIDENCE_ACTION_STORAGE_KEY,
  evidenceActionStageLabel,
  parseEvidenceActionSnapshot,
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
}

export function EvidenceActionProgress({
  requirementId = null,
  jobId = null,
  capability = null,
  requirementText = null,
  stage = null,
  compact = false,
}: EvidenceActionProgressProps) {
  const [snapshot, setSnapshot] = useState<EvidenceActionSnapshot | null>(null);

  useEffect(() => {
    if (requirementId && stage) {
      const next: EvidenceActionSnapshot = {
        requirementId,
        jobId,
        capability,
        requirementText,
        stage,
        updatedAt: Date.now(),
      };
      window.localStorage.setItem(EVIDENCE_ACTION_STORAGE_KEY, JSON.stringify(next));
      setSnapshot(next);
      return;
    }

    const stored = parseEvidenceActionSnapshot(
      window.localStorage.getItem(EVIDENCE_ACTION_STORAGE_KEY),
    );
    if (!stored) {
      window.localStorage.removeItem(EVIDENCE_ACTION_STORAGE_KEY);
    }
    setSnapshot(stored);
  }, [requirementId, jobId, capability, requirementText, stage]);

  if (!snapshot) return null;

  return (
    <section className={compact ? "notice" : "detail-card"} data-testid="evidence-action-progress">
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
    </section>
  );
}

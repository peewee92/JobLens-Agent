"use client";

import Link from "next/link";
import {useEffect, useMemo, useState} from "react";

import type {ApplicationChecklistItem} from "@/lib/application-checklist";
import {
  applicationChecklistFingerprint,
  applicationChecklistStorageKey,
  isApplicationChecklistComplete,
  parseApplicationChecklistState,
  type ApplicationChecklistStepId,
} from "@/lib/application-checklist-state";

export function ApplicationChecklistSummary({
  jobId,
  jobLabel,
  items,
  prepareHref,
  interestedCandidates,
  fallbackHref,
  fallbackLabel,
  fallbackReason,
  batchRemainder,
}: {
  jobId: string;
  jobLabel: string;
  items: ApplicationChecklistItem[];
  prepareHref: string;
  interestedCandidates: Array<{
    jobId: string;
    jobLabel: string;
    prepareHref: string;
    items: ApplicationChecklistItem[] | null;
  }>;
  fallbackHref: string;
  fallbackLabel: string;
  fallbackReason: string;
  batchRemainder: {
    pendingDecision: number;
    matchReady: number;
    requirementBlocked: number;
    evidenceBlocked: number;
    maybe: number;
    unknownReadiness: number;
  };
}) {
  const fingerprint = useMemo(() => applicationChecklistFingerprint(items), [items]);
  const [completed, setCompleted] = useState<ApplicationChecklistStepId[]>([]);

  useEffect(() => {
    const state = parseApplicationChecklistState(
      window.localStorage.getItem(applicationChecklistStorageKey(jobId)),
      fingerprint,
    );
    setCompleted(state.completed);
  }, [jobId, fingerprint]);

  const completedCount = items.filter((item) => completed.includes(item.id)).length;
  const complete = items.length > 0 && completedCount === items.length;
  const nextInterestedCandidate = complete
    ? interestedCandidates.find((candidate) => {
        if (!candidate.items) return true;
        return !isApplicationChecklistComplete(
          window.localStorage.getItem(applicationChecklistStorageKey(candidate.jobId)),
          candidate.items,
        );
      }) ?? null
    : null;

  return (
    <div className="notice" data-testid="application-checklist-summary">
      <strong>{jobLabel} 的申请准备进度：{completedCount}/{items.length}</strong>
      <p className="muted">
        {complete
          ? "当前三项准备任务都已完成。这里只读取本浏览器里、且与当前 JobPreparationBundle 事实指纹一致的 ActionItem 进度，不代表已经投递。"
          : "这是本浏览器里的 ActionItem 进度；只有与当前 JobPreparationBundle 事实指纹一致的勾选才会保留，旧准备事实不会被算进来。"}
      </p>
      {complete && !nextInterestedCandidate ? (
        <div data-testid="application-batch-handoff-summary">
          <p><strong>这批感兴趣岗位的当前申请准备已经收敛。</strong></p>
          <p className="muted">这里只表示当前浏览器中、与最新准备事实一致的清单都已完成，不表示这些岗位已经投递。整个批次接下来还有：</p>
          <div className="summary-grid">
            <div className="summary-card"><span>待投递判断</span><strong>{batchRemainder.pendingDecision}</strong></div>
            <div className="summary-card"><span>可显式 Match</span><strong>{batchRemainder.matchReady}</strong></div>
            <div className="summary-card"><span>Requirement blocker</span><strong>{batchRemainder.requirementBlocked}</strong></div>
            <div className="summary-card"><span>Evidence blocker</span><strong>{batchRemainder.evidenceBlocked}</strong></div>
            <div className="summary-card"><span>保留观察</span><strong>{batchRemainder.maybe}</strong></div>
            {batchRemainder.unknownReadiness > 0 ? (
              <div className="summary-card"><span>暂无法确认</span><strong>{batchRemainder.unknownReadiness}</strong></div>
            ) : null}
          </div>
          <p className="muted"><strong>为什么现在先做这一步：</strong>{fallbackReason}</p>
        </div>
      ) : null}
      <div className="actions">
        {complete ? (
          <>
            {nextInterestedCandidate ? (
              <Link className="button" href={nextInterestedCandidate.prepareHref}>
                {nextInterestedCandidate.items
                  ? `准备下一个尚未完成的感兴趣岗位：${nextInterestedCandidate.jobLabel}`
                  : `检查下一个感兴趣岗位的准备状态：${nextInterestedCandidate.jobLabel}`} →
              </Link>
            ) : (
              <Link className="button" href={fallbackHref}>
                {fallbackLabel} →
              </Link>
            )}
            <Link className="button-secondary" href={prepareHref}>
              查看当前申请准备
            </Link>
          </>
        ) : (
          <Link className="button" href={prepareHref}>
            继续申请准备 →
          </Link>
        )}
      </div>
    </div>
  );
}

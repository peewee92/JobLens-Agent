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

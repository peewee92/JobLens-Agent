"use client";

import Link from "next/link";
import {useEffect, useMemo, useState} from "react";

import type {ApplicationChecklistItem} from "@/lib/application-checklist";
import {
  applicationChecklistFingerprint,
  applicationChecklistStorageKey,
  parseApplicationChecklistState,
  type ApplicationChecklistStepId,
} from "@/lib/application-checklist-state";

export function ApplicationChecklistSummary({
  jobId,
  jobLabel,
  items,
  prepareHref,
}: {
  jobId: string;
  jobLabel: string;
  items: ApplicationChecklistItem[];
  prepareHref: string;
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

  return (
    <div className="notice" data-testid="application-checklist-summary">
      <strong>{jobLabel} 的申请准备进度：{completedCount}/{items.length}</strong>
      <p className="muted">
        {complete
          ? "当前三项准备任务都已完成。这里只读取本浏览器里、且与当前 JobPreparationBundle 事实指纹一致的 ActionItem 进度，不代表已经投递。"
          : "这是本浏览器里的 ActionItem 进度；只有与当前 JobPreparationBundle 事实指纹一致的勾选才会保留，旧准备事实不会被算进来。"}
      </p>
      <div className="actions">
        <Link className={complete ? "button-secondary" : "button"} href={prepareHref}>
          {complete ? "查看当前申请准备" : "继续申请准备"} →
        </Link>
      </div>
    </div>
  );
}

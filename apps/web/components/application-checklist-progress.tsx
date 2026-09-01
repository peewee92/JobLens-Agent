"use client";

import Link from "next/link";
import {useEffect, useMemo, useState} from "react";

import type {ApplicationChecklistItem} from "@/lib/application-checklist";
import {
  applicationChecklistFingerprint,
  applicationChecklistStorageKey,
  parseApplicationChecklistState,
  toggleApplicationChecklistStep,
  type ApplicationChecklistStepId,
} from "@/lib/application-checklist-state";

export function ApplicationChecklistProgress({
  jobId,
  items,
  completionHref,
}: {
  jobId: string;
  items: ApplicationChecklistItem[];
  completionHref?: string;
}) {
  const fingerprint = useMemo(() => applicationChecklistFingerprint(items), [items]);
  const [completed, setCompleted] = useState<ApplicationChecklistStepId[]>([]);

  useEffect(() => {
    const state = parseApplicationChecklistState(
      window.localStorage.getItem(applicationChecklistStorageKey(jobId)),
      fingerprint,
    );
    window.localStorage.setItem(applicationChecklistStorageKey(jobId), JSON.stringify(state));
    setCompleted(state.completed);
  }, [jobId, fingerprint]);

  const checklistComplete = items.length > 0 && items.every((item) => completed.includes(item.id));

  const toggle = (stepId: ApplicationChecklistStepId) => {
    const current = {fingerprint, completed};
    const next = toggleApplicationChecklistStep(current, stepId);
    window.localStorage.setItem(applicationChecklistStorageKey(jobId), JSON.stringify(next));
    setCompleted(next.completed);
  };

  return (
    <section id="application-checklist" className="detail-section" data-testid="application-checklist-progress">
      <div className="section-heading-row">
        <div>
          <h2>申请准备清单</h2>
          <p className="muted">勾选只记录你的准备进度，不会修改 MatchReport、Evidence 或 Ranking。若岗位准备事实发生变化，旧进度会自动重置。</p>
        </div>
        <span className="status-pill">{completed.length}/{items.length} 已完成</span>
      </div>
      <ol>
        {items.map((item) => (
          <li key={item.id}>
            <label>
              <input
                type="checkbox"
                checked={completed.includes(item.id)}
                onChange={() => toggle(item.id)}
              />{" "}
              <strong>{item.label}</strong> {item.text}
            </label>
          </li>
        ))}
      </ol>
      {checklistComplete ? (
        <div className="notice" data-testid="application-checklist-complete">
          <strong>这份岗位申请准备清单已完成</strong>
          <p className="muted">这里只表示你已经处理完当前三项准备任务，不代表系统已经替你投递，也不会改变 MatchReport、Ranking 或 UserFeedback。</p>
          {completionHref ? (
            <div className="actions">
              <Link className="button" href={completionHref}>返回本次导入继续处理 →</Link>
            </div>
          ) : null}
        </div>
      ) : (
        <p className="muted">完成当前三项后，这里会明确提示准备已收敛；如果准备事实发生变化，进度会按新事实自动重置。</p>
      )}
    </section>
  );
}

"use client";

import {useEffect, useMemo, useState} from "react";

import {
  applicationChecklistFingerprint,
  applicationChecklistStorageKey,
  parseApplicationChecklistState,
  toggleApplicationChecklistStep,
  type ApplicationChecklistStepId,
} from "@/lib/application-checklist-state";

interface ChecklistItem {
  id: ApplicationChecklistStepId;
  label: string;
  text: string;
}

export function ApplicationChecklistProgress({jobId, items}: {jobId: string; items: ChecklistItem[]}) {
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
    </section>
  );
}

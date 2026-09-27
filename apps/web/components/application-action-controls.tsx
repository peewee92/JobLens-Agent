"use client";

import {useState} from "react";
import {useRouter} from "next/navigation";

import type {ApplicationExecutionAction} from "@/lib/contracts";

const nextStatus: Record<string, {status: string; label: string} | undefined> = {
  todo: {status: "in_progress", label: "开始行动"},
  in_progress: {status: "done", label: "标记完成"},
};

export function ApplicationActionControls({
  workspaceId,
  actorId,
  actions,
}: {
  workspaceId: string;
  actorId: string;
  actions: ApplicationExecutionAction[];
}) {
  const router = useRouter();
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function request(path: string, body: object, pendingKey: string) {
    setPending(pendingKey);
    setError(null);
    try {
      const response = await fetch(path, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(body),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null) as {detail?: string} | null;
        throw new Error(payload?.detail ?? "操作未完成，请刷新后重试。");
      }
      router.refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "操作未完成，请刷新后重试。");
    } finally {
      setPending(null);
    }
  }

  if (actions.length === 0) {
    return <div className="actions">
      <button
        className="button"
        disabled={pending !== null}
        onClick={() => request(
          `/api/application-workspaces/${encodeURIComponent(workspaceId)}/actions`,
          {actorId, idempotencyKey: `web-study-actions-${workspaceId}`},
          "create",
        )}
      >{pending === "create" ? "正在建立…" : "把学习清单建立为行动"}</button>
      {error ? <p className="error-copy">{error}</p> : null}
    </div>;
  }

  return <>
    {actions.map((action) => {
      const transition = nextStatus[action.status];
      if (!transition) return null;
      const key = `status-${action.actionId}`;
      return <div className="actions" key={action.actionId} style={{marginTop: 8}}>
        <button
          className="button-secondary"
          disabled={pending !== null}
          onClick={() => request(
            `/api/application-workspaces/${encodeURIComponent(workspaceId)}/actions/${encodeURIComponent(action.actionId)}/status`,
            {actorId, expectedStatus: action.status, newStatus: transition.status},
            key,
          )}
        >{pending === key ? "正在更新…" : `${transition.label}：${action.sourceGapCapability ?? action.description}`}</button>
      </div>;
    })}
    {error ? <p className="error-copy">{error}</p> : null}
  </>;
}

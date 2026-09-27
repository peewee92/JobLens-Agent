"use client";

import {useState} from "react";

export function ApplicationWorkspaceEntry({jobId}: {jobId: string}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function openWorkspace() {
    setBusy(true);
    setError(null);
    try {
      const response = await fetch("/api/application-workspaces", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          jobId,
          actorId: "local-user",
          idempotencyKey: `web-application-workspace:${jobId}`,
        }),
      });
      const body = await response.json();
      if (!response.ok || typeof body.workspaceId !== "string") {
        throw new Error(typeof body.detail === "string" ? body.detail : "当前岗位还不能建立求职工作区");
      }
      window.location.assign(`/applications/${encodeURIComponent(body.workspaceId)}`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "当前岗位还不能建立求职工作区");
      setBusy(false);
    }
  }

  return <div>
    <button className="button" type="button" onClick={openWorkspace} disabled={busy}>
      {busy ? "正在打开…" : "进入求职执行工作区 →"}
    </button>
    {error ? <p className="muted" role="alert">{error}</p> : null}
  </div>;
}

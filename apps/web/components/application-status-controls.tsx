"use client";

import {useState} from "react";
import {useRouter} from "next/navigation";

const statusOptions = [
  ["considering", "考虑中"],
  ["preparing", "准备中"],
  ["ready_to_apply", "待投递"],
  ["applied", "已投递"],
  ["interviewing", "面试中"],
  ["offer", "已获 Offer"],
  ["rejected", "未通过"],
  ["withdrawn", "已退出"],
] as const;

export function ApplicationStatusControls({
  workspaceId,
  actorId,
  currentStatus,
}: {
  workspaceId: string;
  actorId: string;
  currentStatus: string;
}) {
  const router = useRouter();
  const [selectedStatus, setSelectedStatus] = useState(currentStatus);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function updateStatus() {
    if (selectedStatus === currentStatus) return;
    setPending(true);
    setError(null);
    const idempotencyKey = `web-application-status-${workspaceId}-${currentStatus}-${selectedStatus}-${Date.now()}`;
    try {
      const response = await fetch(`/api/application-workspaces/${encodeURIComponent(workspaceId)}/status`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          actorId,
          idempotencyKey,
          expectedStatus: currentStatus,
          newStatus: selectedStatus,
        }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null) as {detail?: string} | null;
        throw new Error(payload?.detail ?? "投递状态未更新，请刷新后重试。");
      }
      router.refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "投递状态未更新，请刷新后重试。");
    } finally {
      setPending(false);
    }
  }

  return <div style={{marginTop: 12}}>
    <p className="muted">投递状态只由你显式更新；系统不会因为准备完成、Re-match 或其他内部事件自动标记已投递或面试中。</p>
    <div className="actions">
      <select
        aria-label="投递状态"
        value={selectedStatus}
        disabled={pending}
        onChange={(event) => setSelectedStatus(event.target.value)}
      >
        {statusOptions.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select>
      <button className="button-secondary" disabled={pending || selectedStatus === currentStatus} onClick={updateStatus}>
        {pending ? "正在更新…" : "确认更新投递状态"}
      </button>
    </div>
    {error ? <p className="error-copy">{error}</p> : null}
  </div>;
}

"use client";

import {useEffect, useState} from "react";
import {useProgressRequest} from "./workspace-progress-recovery";


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
  const [selectedStatus, setSelectedStatus] = useState(currentStatus);
  const request = useProgressRequest(workspaceId, 'status');
  useEffect(() => setSelectedStatus(currentStatus), [currentStatus]);
  async function updateStatus() {
    if (selectedStatus === currentStatus) return;
    await request.send({actorId, idempotencyKey: `progress-${crypto.randomUUID()}`,
      expectedStatus: currentStatus, newStatus: selectedStatus});
  }

  return <div style={{marginTop: 12}}>
    <p className="muted">投递状态只由你显式更新；系统不会因为准备完成、重新匹配 或其他内部事件自动标记已投递或面试中。</p>
    <div className="actions">
      <select
        aria-label="投递状态"
        value={selectedStatus}
        disabled={request.disabled}
        onChange={(event) => setSelectedStatus(event.target.value)}
      >
        {statusOptions.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select>
      <button className="button-secondary" disabled={request.disabled || selectedStatus === currentStatus} onClick={updateStatus}>
        {request.busy ? "正在更新…" : "确认更新投递状态"}
      </button>
    </div>
    {request.recovery}
  </div>;
}

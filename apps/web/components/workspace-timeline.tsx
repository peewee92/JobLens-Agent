import type {ApplicationTimelineEvent} from "@/lib/contracts";
import {formatDateTime} from "@/lib/format";

const eventLabels: Record<string, string> = {
  workspace_created: "已创建求职工作区",
  resume_variant_saved: "已保存岗位简历版本",
  action_completed: "已完成一项行动",
  status_changed: "求职状态已更新",
  mock_interview_completed: "已完成一次面试练习",
  evidence_confirmed: "已确认一项职业事实",
  rematch_completed: "已完成岗位重新匹配",
  ranking_changed: "岗位排序发生变化",
};

const statusLabels: Record<string, string> = {
  considering: "考虑中", preparing: "准备中", ready_to_apply: "待投递", applied: "已投递",
  interviewing: "面试中", offer: "已获 Offer", rejected: "未通过", withdrawn: "已退出",
};

function statusLabel(value: string | null): string {
  return value ? statusLabels[value] ?? "未知状态" : "未记录";
}

export function WorkspaceTimeline({events}: {events: ApplicationTimelineEvent[]}) {
  return <section className="detail-section">
    <h2>最近变化</h2>
    {events.length === 0 ? <p className="muted">暂无时间线事件。</p> : <ul>
      {events.slice(-6).reverse().map(event => <li key={event.eventId}>
        {eventLabels[event.eventType] ?? "其他工作区记录"}
        {event.eventType === "status_changed" && <>：{statusLabel(event.fromStatus)} → {statusLabel(event.toStatus)}</>}
        {event.eventType === "workspace_created" && event.toStatus && <>：初始状态为{statusLabel(event.toStatus)}</>}
        {" · "}<time dateTime={event.createdAt}>{formatDateTime(event.createdAt)}</time>
      </li>)}
    </ul>}
  </section>;
}

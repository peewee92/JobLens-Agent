import Link from "next/link";

import {ApplicationActionControls} from "@/components/application-action-controls";
import {ServiceError} from "@/components/service-error";
import {
  BackendApiError,
  fetchApplicationActions,
  fetchApplicationTimeline,
  fetchApplicationWorkspaceOverview,
  fetchJobDetail,
} from "@/lib/backend";
import {userFacingErrorCode} from "@/lib/user-facing-errors";

export const dynamic = "force-dynamic";

const statusLabel: Record<string, string> = {
  considering: "考虑中", preparing: "准备中", ready_to_apply: "待投递", applied: "已投递",
  interviewing: "面试中", offer: "已获 Offer", rejected: "未通过", withdrawn: "已退出",
};

export default async function ApplicationWorkspacePage({params}: {params: Promise<{id: string}>}) {
  const {id} = await params;
  try {
    const overview = await fetchApplicationWorkspaceOverview(id);
    const [job, actions, timeline] = await Promise.all([
      fetchJobDetail(overview.workspace.jobId),
      fetchApplicationActions(id),
      fetchApplicationTimeline(id),
    ]);

    return <>
      <div className="actions" style={{marginBottom: 18}}>
        <Link className="button-ghost" href={`/jobs/${encodeURIComponent(job.id)}`}>← 返回岗位</Link>
        <Link className="button-ghost" href={`/jobs/${encodeURIComponent(job.id)}/prepare`}>查看完整准备依据</Link>
      </div>

      <section className="detail-card">
        <p className="eyebrow">Application Workspace · 求职执行工作区</p>
        <h1>{job.title}</h1>
        <p className="company">{job.company}</p>
        <p className="lede">把这个岗位的简历、面试、行动、Evidence 与投递进度放在同一个事实上下文中；系统不会自动投递或替你确认职业事实。</p>

        <div className="notice">
          <strong>下一步最值得做：{overview.nextBestAction.label}</strong>
          <p className="muted">{overview.nextBestAction.reason}</p>
          <div className="actions"><a className="button" href={overview.nextBestAction.href}>继续这一步 ↓</a></div>
        </div>

        <section className="detail-section">
          <h2>当前执行状态</h2>
          <div className="eligibility-groups">
            <article className="eligibility-result-card"><strong>投递状态</strong><p>{statusLabel[overview.workspace.status] ?? overview.workspace.status}</p></article>
            <article className="eligibility-result-card"><strong>岗位简历</strong><p>{overview.resumeStatus === "reviewed" ? "已人工审核" : overview.resumeStatus === "not_started" ? "尚未开始" : "草稿待审核"}</p></article>
            <article className="eligibility-result-card"><strong>行动事项</strong><p>{overview.actionOpen} 项待完成 / 共 {overview.actionTotal} 项</p></article>
            <article className="eligibility-result-card"><strong>真实 Evidence</strong><p>{overview.evidencePendingConfirmation} 项待确认 / {overview.evidenceConfirmed} 项已确认</p></article>
          </div>
        </section>

        <section className="detail-section" id="resume">
          <h2>岗位简历</h2>
          <p className="muted">只允许把已确认 Evidence 与对应 Requirement 组织进岗位专用版本，不允许用改写掩盖真实能力缺口。</p>
          <Link className="button-secondary" href={`/jobs/${encodeURIComponent(job.id)}/prepare`}>查看简历调整依据 →</Link>
        </section>

        <section className="detail-section" id="actions">
          <h2>执行行动</h2>
          {actions.length === 0 ? <p className="notice">尚未建立可跟踪行动。可以直接把当前 Study Checklist 转成 Action Items。</p> : (
            <div className="eligibility-groups">{actions.map((action) => <article className="eligibility-result-card" key={action.actionId}>
              <strong>{action.sourceGapCapability ?? action.description}</strong>
              <p>{action.description}</p>
              <small className="muted-copy">状态：{action.status} · Requirement：{action.sourceRequirementIds.join("、") || "无"}</small>
            </article>)}</div>
          )}
          <ApplicationActionControls workspaceId={id} actorId={overview.workspace.actorId} actions={actions} />
        </section>

        <section className="detail-section" id="evidence">
          <h2>Evidence 回流</h2>
          <p className="muted">Action 完成不等于获得能力。只有你提交真实经历、显式确认，并再次 Re-match 后，系统才会验证岗位匹配是否真的改善。</p>
          <p>待确认 {overview.evidencePendingConfirmation} 项 · 已确认 {overview.evidenceConfirmed} 项</p>
        </section>

        <section className="detail-section" id="interview">
          <h2>面试练习</h2>
          <p className="muted">练习问题只来自 released JobRequirement 和已确认 Evidence，不重新读取 JD 自由发挥。</p>
          <Link className="button-secondary" href={`/jobs/${encodeURIComponent(job.id)}/prepare`}>查看面试准备事实 →</Link>
        </section>

        <section className="detail-section">
          <h2>最近变化</h2>
          {timeline.length === 0 ? <p className="muted">暂无时间线事件。</p> : <ul>{timeline.slice(-6).reverse().map((event) => <li key={event.eventId}>{event.eventType}{event.fromStatus || event.toStatus ? `：${event.fromStatus ?? "-"} → ${event.toStatus ?? "-"}` : ""}</li>)}</ul>}
        </section>
      </section>
    </>;
  } catch (error) {
    const message = error instanceof BackendApiError
      ? userFacingErrorCode(error.code, "当前求职工作区暂时无法读取，请稍后重试。")
      : "当前求职工作区暂时无法读取，请稍后重试。";
    return <ServiceError message={message} />;
  }
}

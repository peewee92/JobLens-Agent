import Link from "next/link";

import {ApplicationActionControls} from "@/components/application-action-controls";
import {ApplicationEvidenceControls} from "@/components/application-evidence-controls";
import {ApplicationInterviewControls} from "@/components/application-interview-controls";
import {ApplicationResumeControls} from "@/components/application-resume-controls";
import {ApplicationStatusControls} from "@/components/application-status-controls";
import {ServiceError} from "@/components/service-error";
import {systemReadinessNotice} from "@/components/system-readiness-notice";
import {
  BackendApiError,
  fetchApplicationActions,
  fetchApplicationEvidenceProposals,
  fetchApplicationEvidenceContext,
  fetchApplicationInterviewQuestions,
  fetchApplicationResumeVariantProposal,
  fetchApplicationResumeVariants,
  fetchApplicationTimeline,
  fetchApplicationWorkspaceOverview,
  fetchJobDetail,
  fetchWorkspaceSavedPreparation,
} from "@/lib/backend";
import {prioritizeApplicationActions, actionStatusLabels, actionPurposeLabels} from "@/lib/application-actions";
import type {ApplicationExecutionAction} from "@/lib/contracts";
import {userFacingErrorCode} from "@/lib/user-facing-errors";

export const dynamic = "force-dynamic";

const statusLabel: Record<string, string> = {
  considering: "考虑中", preparing: "准备中", ready_to_apply: "待投递", applied: "已投递",
  interviewing: "面试中", offer: "已获 Offer", rejected: "未通过", withdrawn: "已退出",
};

export default async function ApplicationWorkspacePage({params}: {params: Promise<{id: string}>}) {
  const {id} = await params;
  const notice = await systemReadinessNotice(`/applications/${encodeURIComponent(id)}`);
  if (notice) return notice;
  try {
    const overview = await fetchApplicationWorkspaceOverview(id);
    const [job, actions, proposals, timeline, resumeProposal, resumeVariants, interviewQuestions] = await Promise.all([
      fetchJobDetail(overview.workspace.jobId),
      fetchApplicationActions(id),
      fetchApplicationEvidenceProposals(id),
      fetchApplicationTimeline(id),
      fetchApplicationResumeVariantProposal(id),
      fetchApplicationResumeVariants(id),
      fetchApplicationInterviewQuestions(id),
    ]);
    const currentResumeVariant = resumeVariants.at(-1) ?? null;
    const savedPreparation = overview.workspace.currentAnalysisThreadId ? await fetchWorkspaceSavedPreparation(id) : null;
    const evidenceContext = await fetchApplicationEvidenceContext(id);
    const orderedActions = prioritizeApplicationActions(actions);
    const renderAction = (action: ApplicationExecutionAction) => <article className="eligibility-result-card" key={action.actionId}>
      <strong>{action.sourceGapCapability ?? action.description}</strong>
      <p>{action.description}</p>
      <p>目的：{actionPurposeLabels[action.actionType] ?? "岗位准备"} · 状态：{actionStatusLabels[action.status] ?? "待核实"}</p>
      <ul>{action.completionCriteria.map((criterion, index) => <li key={index}>{criterion}</li>)}</ul>
      <small className="muted-copy">来源岗位要求：{action.sourceRequirementIds.join("、") || "无"}</small>
      {action.sourceAnalysisThreadId && <p><Link href={`/agent/results/${encodeURIComponent(action.sourceAnalysisThreadId)}`}>查看行动创建时的分析与事实</Link></p>}
      <ApplicationActionControls workspaceId={id} actorId={overview.workspace.actorId} actions={[action]} />
    </article>;


    return <>
      <div className="actions" style={{marginBottom: 18}}>
        <Link className="button-ghost" href={`/jobs/${encodeURIComponent(job.id)}`}>← 返回岗位</Link>
        <Link className="button-ghost" href={savedPreparation ? `/agent/results/${encodeURIComponent(savedPreparation.threadId)}` : `/jobs/${encodeURIComponent(job.id)}/prepare`}>{savedPreparation ? "查看本次保存的准备依据" : "按当前资料查看准备依据"}</Link>
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

        {savedPreparation && <section className="detail-section">
          <h2>已保存的准备材料</h2>
          <div className="actions"><Link className="button-secondary" href={`/agent/results/${encodeURIComponent(savedPreparation.threadId)}/update`}>核对范围并更新分析</Link><Link href="/">返回求职工作台</Link></div>
          <p>职业资料 v{savedPreparation.preparation.profileVersion} · 来自确认目标时保存的分析，不会在打开工作区时重算。</p>
          {!savedPreparation.isCurrent && <p className="notice">当前事实已变化。这些历史材料仍可查看，投递结果和行动进度仍可记录；请更新分析后再建立新材料。</p>}
          <Link href={`/agent/results/${encodeURIComponent(savedPreparation.threadId)}`}>打开原始分析、差距与完整准备材料</Link>
        </section>}

        <section className="detail-section">
          <h2>当前执行状态</h2>
          <div className="eligibility-groups">
            <article className="eligibility-result-card"><strong>投递状态</strong><p>{statusLabel[overview.workspace.status] ?? overview.workspace.status}</p></article>
            <article className="eligibility-result-card"><strong>岗位简历</strong><p>{overview.resumeStatus === "reviewed" ? "已人工审核" : overview.resumeStatus === "not_started" ? "尚未开始" : "草稿待审核"}</p></article>
            <article className="eligibility-result-card"><strong>行动事项</strong><p>{overview.actionOpen} 项待完成 / 共 {overview.actionTotal} 项</p></article>
            <article className="eligibility-result-card"><strong>真实 Evidence</strong><p>{overview.evidencePendingConfirmation} 项待确认 / {overview.evidenceConfirmed} 项已确认</p></article>
          </div>
          <ApplicationStatusControls
            workspaceId={id}
            actorId={overview.workspace.actorId}
            currentStatus={overview.workspace.status}
          />
        </section>

        <section className="detail-section" id="resume">
          <h2>岗位简历</h2>
          <p className="muted">只允许把已确认 Evidence 与对应 Requirement 组织进岗位专用版本，不允许用改写掩盖真实能力缺口。</p>
          <ApplicationResumeControls
            workspaceId={id}
            actorId={overview.workspace.actorId}
            proposal={resumeProposal}
            currentVariant={currentResumeVariant}
          />
          <div className="actions"><Link className="button-ghost" href={savedPreparation ? `/agent/results/${encodeURIComponent(savedPreparation.threadId)}` : `/jobs/${encodeURIComponent(job.id)}/prepare`}>{savedPreparation ? "查看本次保存的简历事实依据 →" : "按当前资料查看简历调整依据 →"}</Link></div>
        </section>

        <section className="detail-section" id="actions">
          <h2>执行行动</h2>
          {actions.length === 0 ? <>
            <p className="notice">尚未建立可跟踪行动，可以从已有准备材料建立清单。</p>
            <ApplicationActionControls workspaceId={id} actorId={overview.workspace.actorId} actions={actions} />
          </> : <>
            <p className="muted">先显示最重要的 3 项：进行中的行动优先，再核实证据、学习实践和准备材料。完成行动不会自动改变职业事实。</p>
            <div className="eligibility-groups">{orderedActions.slice(0, 3).map(renderAction)}</div>
            {orderedActions.length > 3 && <details><summary>展开其余 {orderedActions.length - 3} 项行动</summary>
              <div className="eligibility-groups">{orderedActions.slice(3).map(renderAction)}</div>
            </details>}
          </>}
        </section>

        <section className="detail-section" id="evidence">
          <h2>Evidence 回流</h2>
          <p className="muted">行动完成不等于获得能力。只有你提交真实经历并显式确认，再更新分析，才能核对判断变化；结论可能改善、未变或变弱。</p>
          <p>待确认 {overview.evidencePendingConfirmation} 项 · 已确认 {overview.evidenceConfirmed} 项</p>
          <ApplicationEvidenceControls workspaceId={id} actorId={overview.workspace.actorId} actions={actions} proposals={proposals} context={evidenceContext} analysisThreadId={overview.workspace.currentAnalysisThreadId} />
        </section>

        <section className="detail-section" id="interview">
          <h2>面试练习</h2>
          <p className="muted">练习问题只来自 released JobRequirement 和已确认 Evidence，不重新读取 JD 自由发挥；回答审核只检查真实 Evidence grounding，不伪造录用概率或语义评分。</p>
          <ApplicationInterviewControls workspaceId={id} actorId={overview.workspace.actorId} questionSet={interviewQuestions} />
          <div className="actions"><Link className="button-ghost" href={savedPreparation ? `/agent/results/${encodeURIComponent(savedPreparation.threadId)}` : `/jobs/${encodeURIComponent(job.id)}/prepare`}>{savedPreparation ? "查看本次保存的面试准备事实 →" : "按当前资料查看面试准备事实 →"}</Link></div>
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

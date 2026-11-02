import {publicDemoEnabled} from "@/lib/public-demo";
import Link from "next/link";

import {LegacyAnalysisStart} from "@/components/legacy-analysis-start";
import {reasonLabels} from "@/components/analysis-update-plan-view";
import {ApplicationActionControls} from "@/components/application-action-controls";
import {ApplicationEvidenceControls} from "@/components/application-evidence-controls";
import {ApplicationInterviewControls} from "@/components/application-interview-controls";
import {ApplicationResumeControls} from "@/components/application-resume-controls";
import {ApplicationStatusControls} from "@/components/application-status-controls";
import {ServiceError} from "@/components/service-error";
import {WorkspaceTimeline} from "@/components/workspace-timeline";
import {systemReadinessNotice} from "@/components/system-readiness-notice";
import {
  BackendApiError,
  fetchApplicationActions,
  fetchAnalysisExecution,
  fetchApplicationEvidenceProposals,
  fetchApplicationEvidenceContext,
  fetchApplicationInterviewQuestions,
  fetchApplicationResumeVariantProposal,
  fetchApplicationResumeVariants,
  fetchApplicationTimeline,
  fetchApplicationWorkspaceOverview,
  fetchJobDetail,
  fetchLegacyWorkspaceAnalysisPlan,
  fetchWorkspaceSavedPreparation,
} from "@/lib/backend";
import {actionStatusLabels, actionPurposeLabels} from "@/lib/application-actions";
import {currentExecutionActionIds, groupWorkspaceActions} from "@/lib/workspace-analysis-display";
import type {ApplicationExecutionAction} from "@/lib/contracts";
import {userFacingErrorCode} from "@/lib/user-facing-errors";
import {readOptionalPreparation} from "@/lib/workspace-optional-preparation";

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
    if (publicDemoEnabled()) {
      const [job, actions] = await Promise.all([fetchJobDetail(overview.workspace.jobId), fetchApplicationActions(id)]);
      const threadId = overview.workspace.currentAnalysisThreadId;
      return <section className="card stack-md"><p className="eyebrow">合成样本 · 我的准备</p><h1>{job.title}</h1>
        <p>下一步：开始一项准备行动，再刷新检查进度。完成行动只是进度，不会自动变成职业经历。</p>
        {threadId && <Link href={`/agent/results/${encodeURIComponent(threadId)}`}>查看保存的依据与准备材料</Link>}
        <h2>准备行动</h2>
        {actions.map(action => <article className="card" key={action.actionId}><h3>{action.sourceGapCapability ?? action.description}</h3>
          <p>状态：{actionStatusLabels[action.status] ?? "待核对"}</p>
          <ApplicationActionControls workspaceId={id} actorId="local-user" actions={[action]} /></article>)}
        {!actions.length && <p>尚无保存的行动，请返回已保存分析，明确开始执行。</p>}
        <p>公开演示不开放私人事实、简历上传、投递状态修改或模型调用。临时进度在会话过期或服务重启后重置。</p>
        <Link href="/applications">查看我的准备</Link><Link href="/">返回首页</Link></section>;
    }

    const [job, actions, proposals, timeline, resumeProposal, resumeVariants, interviewQuestions] = await Promise.all([
      fetchJobDetail(overview.workspace.jobId),
      fetchApplicationActions(id),
      fetchApplicationEvidenceProposals(id),
      fetchApplicationTimeline(id),
      readOptionalPreparation(() => fetchApplicationResumeVariantProposal(id)),
      fetchApplicationResumeVariants(id),
      readOptionalPreparation(() => fetchApplicationInterviewQuestions(id)),
    ]);
    const currentResumeVariant = resumeVariants.at(-1) ?? null;
    const savedPreparation = overview.workspace.currentAnalysisThreadId ? await fetchWorkspaceSavedPreparation(id) : null;
    const evidenceContext = await fetchApplicationEvidenceContext(id);
    let legacyPlan: import("@/lib/contracts").LegacyWorkspaceAnalysisPlan | null = null;
    let legacyPlanUnavailable = false;
    if (!overview.workspace.currentAnalysisThreadId && proposals.some(item => item.status === "confirmed")) {
      try { legacyPlan = await fetchLegacyWorkspaceAnalysisPlan(id); }
      catch { legacyPlanUnavailable = true; }
    }
    let currentActionIds: string[] | null = null;
    if (overview.workspace.currentAnalysisThreadId && overview.workspace.currentAnalysisResultId) {
      try {
        const {execution} = await fetchAnalysisExecution(overview.workspace.currentAnalysisThreadId);
        currentActionIds = currentExecutionActionIds(execution, overview.workspace.currentAnalysisResultId, id);
      } catch { /* Keep actions usable even when their current association cannot be read. */ }
    }
    const groupedActions = groupWorkspaceActions(actions, overview.workspace.currentAnalysisResultId, currentActionIds);
    const renderAction = (action: ApplicationExecutionAction) => <article className="eligibility-result-card" key={action.actionId}>
      <strong>{action.sourceGapCapability ?? action.description}</strong>
      <p>{action.description}</p>
      <p>目的：{actionPurposeLabels[action.actionType] ?? "岗位准备"} · 状态：{actionStatusLabels[action.status] ?? "待核实"}</p>
      <ul>{action.completionCriteria.map((criterion, index) => <li key={index}>{criterion}</li>)}</ul>
      <small className="muted-copy">来源岗位要求：{action.sourceRequirementIds.join("、") || "无"}</small>
      {currentActionIds?.includes(action.actionId) && action.sourceAnalysisResultId !== overview.workspace.currentAnalysisResultId && <p>本次分析复用了这项行动；原有进度与创建来源保留。</p>}
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

        {legacyPlan && <section className="detail-section" aria-label="历史岗位分析预检">
          <h2>这份历史岗位还能怎样分析</h2>
          <p>当前资料 v{legacyPlan.profileVersion ?? "未确认"}。这里只检查输入，不保存结果、不运行匹配或调用模型；执行前仍需重新核对。</p>
          <p>{({reuse: "已有匹配报告与当前输入兼容", ready: "已有报告已变化，可由规则重算", deferred: "当前不在可处理范围", requires_model: "需要语义判断，尚未授权模型调用", input_blocked: "输入尚未准备好，需要先修复"} as const)[legacyPlan.item.status]}。</p>
          {(legacyPlan.item.staleReasons.length > 0 || legacyPlan.item.blockerCodes.length > 0) && <details><summary>查看版本变化与阻断原因</summary><p>{[...legacyPlan.item.staleReasons, ...legacyPlan.item.blockerCodes].map(code => reasonLabels[code] ?? `需要核对的输入（${code}）`).join("、")}</p></details>}
          <LegacyAnalysisStart plan={legacyPlan} />
          <Link href={legacyPlan.item.repairHref}>核对岗位或修复输入</Link>
        </section>}
        {legacyPlanUnavailable && <p className="notice">暂时无法检查历史岗位的分析条件；历史记录不受影响。请稍后刷新重试，不会自动执行分析。</p>}

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
          {resumeProposal ? <ApplicationResumeControls
            workspaceId={id}
            actorId={overview.workspace.actorId}
            proposal={resumeProposal}
            currentVariant={currentResumeVariant}
          /> : <p className="notice">职业事实已变化，不能按旧版本生成新简历材料。已有简历状态：{currentResumeVariant ? (currentResumeVariant.status === "reviewed" ? "已人工审核" : "草稿待审核") : "尚未保存"}；历史记录仍保留，请更新或重新创建分析。</p>}
          <div className="actions"><Link className="button-ghost" href={savedPreparation ? `/agent/results/${encodeURIComponent(savedPreparation.threadId)}` : `/jobs/${encodeURIComponent(job.id)}/prepare`}>{savedPreparation ? "查看本次保存的简历事实依据 →" : "按当前资料查看简历调整依据 →"}</Link></div>
        </section>

        <section className="detail-section" id="actions">
          <h2>执行行动</h2>
          {actions.length === 0 ? <>
            <p className="notice">尚未建立可跟踪行动，可以从已有准备材料建立清单。</p>
            <ApplicationActionControls workspaceId={id} actorId={overview.workspace.actorId} actions={actions} />
          </> : <>
            <p className="muted">当前分析关联的行动优先显示，可能复用较早行动及其进度；其余行动仍保留。完成行动不会自动改变职业事实。</p>
            {overview.workspace.currentAnalysisResultId && <h3>当前分析的行动</h3>}
            {overview.workspace.currentAnalysisResultId && currentActionIds === null && <p className="notice">暂时无法核对本次分析复用的行动，以下按创建来源分组；所有行动和进度仍可查看。</p>}
            {groupedActions.current.length === 0 && <p>当前分析没有关联行动；可查看下方已有行动。</p>}
            <div className="eligibility-groups">{groupedActions.current.slice(0, 3).map(renderAction)}</div>
            {groupedActions.current.length > 3 && <details><summary>展开其余 {groupedActions.current.length - 3} 项行动</summary>
              <div className="eligibility-groups">{groupedActions.current.slice(3).map(renderAction)}</div>
            </details>}
            {groupedActions.earlier.length > 0 && <details><summary>查看较早分析或未标明来源的行动（{groupedActions.earlier.length}）</summary>
              <p>这些行动可能与当前建议相似，但有独立的来源和进度，仍可操作。</p>
              <div className="eligibility-groups">{groupedActions.earlier.map(renderAction)}</div>
            </details>}
          </>}
        </section>

        <section className="detail-section" id="evidence">
          <h2>Evidence 回流</h2>
          <p className="muted">行动完成不等于获得能力。只有你提交真实经历并显式确认，再更新分析，才能核对判断变化；结论可能改善、未变或变弱。</p>
          <p>待确认 {overview.evidencePendingConfirmation} 项 · 已确认 {overview.evidenceConfirmed} 项</p>
          <ApplicationEvidenceControls workspaceId={id} jobId={job.id} actorId={overview.workspace.actorId} actions={actions} proposals={proposals} context={evidenceContext} analysisThreadId={overview.workspace.currentAnalysisThreadId} analysisProfileVersion={savedPreparation?.preparation.profileVersion} />
        </section>

        <section className="detail-section" id="interview">
          <h2>面试练习</h2>
          <p className="muted">练习问题只来自 released JobRequirement 和已确认 Evidence，不重新读取 JD 自由发挥；回答审核只检查真实 Evidence grounding，不伪造录用概率或语义评分。</p>
          {interviewQuestions ? <ApplicationInterviewControls workspaceId={id} actorId={overview.workspace.actorId} questionSet={interviewQuestions} /> : <p className="notice">职业事实已变化，暂不生成新的面试练习；请更新或重新创建分析。</p>}
          <div className="actions"><Link className="button-ghost" href={savedPreparation ? `/agent/results/${encodeURIComponent(savedPreparation.threadId)}` : `/jobs/${encodeURIComponent(job.id)}/prepare`}>{savedPreparation ? "查看本次保存的面试准备事实 →" : "按当前资料查看面试准备事实 →"}</Link></div>
        </section>

        <WorkspaceTimeline events={timeline} />
      </section>
    </>;
  } catch (error) {
    const message = error instanceof BackendApiError
      ? userFacingErrorCode(error.code, "当前求职工作区暂时无法读取，请稍后重试。")
      : "当前求职工作区暂时无法读取，请稍后重试。";
    return <ServiceError message={message} />;
  }
}

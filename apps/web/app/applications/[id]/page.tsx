import {workspacePath} from "@/lib/workspace-path";
import {preparationFacts} from "@/lib/preparation-facts";
import {completionCriterionLabel} from "@/lib/gap-language";
import {formatDateTime} from "@/lib/format";
import {WorkspaceRecordBrowser} from "@/components/workspace-record-browser";
import {publicDemoEnabled} from "@/lib/public-demo";
import Link from "next/link";
import {Button} from "@/components/ui/button";
import {PageHeading} from "@/components/ui/patterns";
import {Badge, Panel} from "@/components/ui/primitives";

import {LegacyAnalysisStart} from "@/components/legacy-analysis-start";
import {reasonLabels} from "@/components/analysis-update-plan-view";
import {ApplicationActionControls} from "@/components/application-action-controls";
import {ApplicationEvidenceControls} from "@/components/application-evidence-controls";
import {ApplicationInterviewControls} from "@/components/application-interview-controls";
import {ApplicationResumeControls} from "@/components/application-resume-controls";
import {ApplicationStatusControls} from "@/components/application-status-controls";
import {ServiceError} from "@/components/service-error";
import {WorkspaceSections} from "@/components/workspace-sections";
import {WorkspaceTaskList} from "@/components/workspace-task-list";
import {DetailDrawer} from "@/components/ui/drawer";
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
  fetchJobPreparation,
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
        <Link href="/applications">查看我的准备</Link><a href={workspacePath("/")}>返回首页</a></section>;
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
    const [savedPreparation, evidenceContext, currentPreparation] = await Promise.all([
      overview.workspace.currentAnalysisThreadId ? fetchWorkspaceSavedPreparation(id) : null,
      fetchApplicationEvidenceContext(id),
      resumeProposal || interviewQuestions ? fetchJobPreparation(job.id).catch(() => null) : null,
    ]);
    const attachFacts = (source: {sourceProfileId: string; sourceProfileVersion: number; requirementExtractionId: string} | null) =>
      preparationFacts(source ? [savedPreparation?.preparation, currentPreparation].find(candidate => candidate?.jobId === job.id
        && candidate.profileId === source.sourceProfileId && candidate.profileVersion === source.sourceProfileVersion
        && candidate.extractionId === source.requirementExtractionId) : null);
    const historicalPreparation = savedPreparation?.isCurrent === false;
    const resumeFacts = attachFacts(resumeProposal);
    const interviewFacts = attachFacts(interviewQuestions);
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
    const actionDetail = (action: ApplicationExecutionAction) => <>
      <p>目的：{actionPurposeLabels[action.actionType] ?? "岗位准备"} · 状态：{actionStatusLabels[action.status] ?? "待核实"}</p>
      {action.completionCriteria.length > 0 && <details><summary>查看完成标准</summary><ul>{action.completionCriteria.map((criterion, index) => <li key={index}>{completionCriterionLabel(criterion)}</li>)}</ul></details>}
      {action.sourceRequirementIds.length > 0 && <p className="muted-copy">关联 {action.sourceRequirementIds.length} 条岗位要求。{!action.sourceAnalysisThreadId && <Link href={`/jobs/${encodeURIComponent(job.id)}/prepare`}>核对岗位准备依据</Link>}</p>}
      {currentActionIds?.includes(action.actionId) && action.sourceAnalysisResultId !== overview.workspace.currentAnalysisResultId && <p>本次分析复用了这项行动；原有进度与创建来源保留。</p>}
      {action.sourceAnalysisThreadId && <p><Link href={`/agent/results/${encodeURIComponent(action.sourceAnalysisThreadId)}`}>查看行动创建时的分析与事实</Link></p>}
    </>;


    return <>
      <div className="jl-workspace-breadcrumb">
        <Button variant="subtle" asChild><Link href="/applications">我的准备 <span aria-hidden="true">›</span></Link></Button>
        <div className="jl-inline">
          <Button variant="subtle" asChild><Link href={savedPreparation ? `/agent/results/${encodeURIComponent(savedPreparation.threadId)}` : `/jobs/${encodeURIComponent(job.id)}/prepare`}>{savedPreparation ? "原始分析" : "准备依据"}</Link></Button>
          <DetailDrawer trigger={<Button variant="subtle">最近变化</Button>} title="最近变化" description="这里显示已保存的进度，不会重新分析。">
            <WorkspaceTimeline events={timeline} inDrawer />
          </DetailDrawer>
        </div>
      </div>
      <div className="jl-workspace-hero">
        <div>
          <PageHeading kicker="岗位准备工作区" title={job.title} description={job.company} />
          <div className="jl-inline">
            <Badge tone="info">{statusLabel[overview.workspace.status] ?? "状态待核实"}</Badge>
            {savedPreparation && historicalPreparation && <Badge tone="warning">资料已变化</Badge>}
            <span className="muted-copy">系统不会替你投递或确认经历。</span>
          </div>
        </div>
        <Panel className="jl-workbench-focus jl-workspace-next" aria-labelledby="workspace-next-title">
          <div className="stack-sm">
            <p className="jl-kicker">建议下一步</p>
            {savedPreparation && historicalPreparation ? <>
              <h2 id="workspace-next-title">先核对变化的事实</h2>
              <p>已有记录仍可查看。建立新材料前，请先更新依据。</p>
            </> : <>
              <h2 id="workspace-next-title">{overview.nextBestAction.label}</h2>
              <p>{overview.nextBestAction.reason}</p>
            </>}
          </div>
          {savedPreparation && historicalPreparation ?
            <Button asChild><Link href={`/agent/results/${encodeURIComponent(savedPreparation.threadId)}/update`}>核对并更新分析</Link></Button>
            : <Button asChild><a href={workspacePath(overview.nextBestAction.href)}>继续这一步 <span aria-hidden="true">→</span></a></Button>}
        </Panel>
      </div>

      <WorkspaceSections recommended={overview.nextBestAction.href.split("#")[1]} panels={{
        resume: <section className="detail-section" id="resume" tabIndex={-1} aria-labelledby="workspace-resume-heading">
          <h2 id="workspace-resume-heading">岗位简历</h2>
          <p className="muted">只把已确认的经历与对应岗位要求组织成专用草稿，不允许用改写掩盖真实能力缺口。</p>
          {resumeProposal ? <ApplicationResumeControls
            workspaceId={id}
            actorId={overview.workspace.actorId}
            proposal={resumeProposal}
            currentVariant={currentResumeVariant}
            facts={resumeFacts}
            historical={historicalPreparation}
          /> : <p className="notice">职业事实已变化，不能按旧版本生成新简历材料。已有简历状态：{currentResumeVariant ? (currentResumeVariant.status === "reviewed" ? "已人工审核" : "草稿待审核") : "尚未保存"}；历史记录仍保留，请更新或重新创建分析。</p>}
          {resumeVariants.length > 0 && <details>
            <summary>查看已保存的简历版本（{resumeVariants.length} 份）</summary>
            <p>以下是当时保存的事实，不会变成当前建议。只有最新有效的资料可以建立新材料。</p>
            <WorkspaceRecordBrowser label="简历版本列表" records={[...resumeVariants].reverse().map(variant => ({
              id: variant.variantId,
              title: formatDateTime(variant.createdAt),
              summary: `职业背景第 ${variant.sourceProfileVersion} 版 · ${variant.status === "reviewed" ? "已人工核对" : "已保存草稿"}`,
              content: <div className="stack-sm"><Badge>已保存版本</Badge><h3>{formatDateTime(variant.createdAt)}</h3>
                <ul>{variant.highlights.map(item => <li key={item.requirementId}>{item.capability} · 当时关联 {item.evidenceIds.length} 条经历</li>)}</ul>
              </div>,
            }))} />
          </details>}
          <div className="actions"><Link className="button-ghost" href={savedPreparation ? `/agent/results/${encodeURIComponent(savedPreparation.threadId)}` : `/jobs/${encodeURIComponent(job.id)}/prepare`}>{savedPreparation ? "查看本次保存的简历事实依据 →" : "按当前资料查看简历调整依据 →"}</Link></div>
        </section>,
        actions: <section className="detail-section" id="actions" tabIndex={-1} aria-labelledby="workspace-actions-heading">
          <h2 id="workspace-actions-heading">执行行动</h2>
          {actions.length === 0 ? <>
            <p className="notice">{historicalPreparation ? "还没有行动。请先更新分析，再依据当前事实建立清单。" : "尚未建立可跟踪行动，可以从已有准备材料建立清单。"}</p>
            {!historicalPreparation && <ApplicationActionControls workspaceId={id} actorId={overview.workspace.actorId} actions={actions} />}
          </> : <>
            <p className="muted">当前分析关联的行动优先显示，可能复用较早行动及其进度；其余行动仍保留。完成行动不会自动改变职业事实。</p>
            {overview.workspace.currentAnalysisResultId && <h3>当前分析的行动</h3>}
            {overview.workspace.currentAnalysisResultId && currentActionIds === null && <p className="notice">暂时无法核对本次分析复用的行动，以下按创建来源分组；所有行动和进度仍可查看。</p>}
            {groupedActions.current.length === 0 && <p>当前分析没有关联行动；可查看下方已有行动。</p>}
            {groupedActions.current.length > 0 && <WorkspaceTaskList items={groupedActions.current.map(action => ({action, detail: actionDetail(action)}))} workspaceId={id} actorId={overview.workspace.actorId} />}
            {groupedActions.earlier.length > 0 && <details><summary>查看较早分析或未标明来源的行动（{groupedActions.earlier.length}）</summary>
              <p>这些行动有独立的来源和进度，不代表本次分析得出了同样结论。</p>
              <WorkspaceTaskList items={groupedActions.earlier.map(action => ({action, detail: actionDetail(action)}))} workspaceId={id} actorId={overview.workspace.actorId} />
            </details>}
          </>}
        </section>,
        evidence: <section className="detail-section" id="evidence" tabIndex={-1} aria-labelledby="workspace-evidence-heading">
          <h2 id="workspace-evidence-heading">补充真实经历</h2>
          <p className="muted">行动完成不等于获得能力。只有你提交真实经历并显式确认，再更新分析，才能核对判断变化；结论可能改善、未变或变弱。</p>
          <p>待确认 {overview.evidencePendingConfirmation} 项 · 已确认 {overview.evidenceConfirmed} 项</p>
          <ApplicationEvidenceControls workspaceId={id} jobId={job.id} actorId={overview.workspace.actorId} actions={actions} proposals={proposals} context={evidenceContext} analysisThreadId={overview.workspace.currentAnalysisThreadId} analysisProfileVersion={savedPreparation?.preparation.profileVersion} />
        </section>,
        interview: <section className="detail-section" id="interview" tabIndex={-1} aria-labelledby="workspace-interview-heading">
          <h2 id="workspace-interview-heading">面试练习</h2>
          <p className="muted">问题来自已核对的岗位要求。回答只核对已确认的经历是否可引用，不打面试分，也不预测录用。</p>
          {interviewQuestions ? <ApplicationInterviewControls workspaceId={id} actorId={overview.workspace.actorId} questionSet={interviewQuestions} evidenceSummaries={interviewFacts.evidenceSummaries} historical={historicalPreparation} /> : <p className="notice">职业事实已变化，暂不生成新的面试练习；请更新或重新创建分析。</p>}
          <div className="actions"><Link className="button-ghost" href={savedPreparation ? `/agent/results/${encodeURIComponent(savedPreparation.threadId)}` : `/jobs/${encodeURIComponent(job.id)}/prepare`}>{savedPreparation ? "查看本次保存的面试准备事实 →" : "按当前资料查看面试准备事实 →"}</Link></div>
        </section>,
      }} />

      <details className="jl-panel jl-workspace-management">
        <summary>管理投递状态与历史分析</summary>
        <div className="jl-inline"><Link href={`/jobs/${encodeURIComponent(job.id)}`}>查看岗位详情</Link></div>
        {savedPreparation && <section className="detail-section">
          <h2>已保存的准备材料</h2>
          <div className="actions"><Link className="button-secondary" href={`/agent/results/${encodeURIComponent(savedPreparation.threadId)}/update`}>核对范围并更新分析</Link><a href={workspacePath("/")}>返回求职工作台</a></div>
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
            <article className="eligibility-result-card"><strong>真实经历</strong><p>{overview.evidencePendingConfirmation} 项待确认 / {overview.evidenceConfirmed} 项已确认</p></article>
          </div>
          <ApplicationStatusControls
            workspaceId={id}
            actorId={overview.workspace.actorId}
            currentStatus={overview.workspace.status}
          />
        </section>

      </details>

    </>;
  } catch (error) {
    const message = error instanceof BackendApiError
      ? userFacingErrorCode(error.code, "当前求职工作区暂时无法读取，请稍后重试。")
      : "当前求职工作区暂时无法读取，请稍后重试。";
    return <ServiceError message={message} />;
  }
}

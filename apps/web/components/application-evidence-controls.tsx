"use client";

import Link from "next/link";
import React, {FormEvent, useEffect, useState} from "react";
import {useRouter} from "next/navigation";
import {workspaceCommandError} from "@/lib/workspace-command-errors";
import {readWorkspaceFactCommand, clearWorkspaceFactCommand, sendWorkspaceFactCommand, type WorkspaceFactCommand} from "@/lib/workspace-fact-command";
import type {ApplicationEvidenceContext, ApplicationEvidenceProposal, ApplicationExecutionAction, ApplicationRematchResult} from "@/lib/contracts";

export function ApplicationEvidenceControls({workspaceId, actorId, actions, proposals, context, analysisThreadId}: {
  workspaceId: string; actorId: string; actions: ApplicationExecutionAction[];
  proposals: ApplicationEvidenceProposal[]; context: ApplicationEvidenceContext; analysisThreadId?: string | null;
}) {
  const router = useRouter();
  const [rematchResult, setRematchResult] = useState<ApplicationRematchResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [original, setOriginal] = useState<WorkspaceFactCommand | null>(null);
  const [storageError, setStorageError] = useState(false);
  useEffect(() => {
    try { setOriginal(readWorkspaceFactCommand(window.localStorage, workspaceId)); }
    catch { setStorageError(true); setError("浏览器无法读取待确认请求，请先刷新核对服务端提案。"); }
  }, [workspaceId]);
  const proposalActionIds = new Set(proposals.map(item => item.actionId));
  const sources = new Map(context.actionSources.map(source => [source.actionId, source]));
  const eligibleActions = actions.filter(item => item.status === "done" && sources.has(item.actionId) && !proposalActionIds.has(item.actionId));
  const currentId = context.currentProfileId, currentVersion = context.currentProfileVersion;

  async function post(path: string, body: Record<string, unknown>, existing?: WorkspaceFactCommand) {
    setBusy(true); setError(null);
    const command = existing ?? {version: 1 as const, workspaceId, commandId: crypto.randomUUID(), path, body};
    try {
      const response = await sendWorkspaceFactCommand(window.localStorage, command);
      const payload = await response.json().catch(() => null);
      if (!response.ok) throw new Error(workspaceCommandError(payload));
      router.refresh();
    } catch (caught) { setError(caught instanceof Error ? caught.message : "保存结果未确认，请查询提案后重试原请求。"); }
    finally {
      try { setOriginal(readWorkspaceFactCommand(window.localStorage, workspaceId)); } catch { setStorageError(true); }
      setBusy(false);
    }
  }

  async function rematch(proposal: ApplicationEvidenceProposal) {
    setBusy(true); setError(null);
    try {
      const response = await fetch(`/api/application-workspaces/${encodeURIComponent(workspaceId)}/evidence-proposals/${encodeURIComponent(proposal.proposalId)}/rematch`, {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({actorId, idempotencyKey: `web-rematch-${proposal.proposalId}`}),
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok) throw new Error(workspaceCommandError(payload));
      setRematchResult(payload); router.refresh();
    } catch (caught) { setError(caught instanceof Error ? caught.message : "重新匹配未完成，请核对输入。"); }
    finally { setBusy(false); }
  }

  function submitProposal(event: FormEvent<HTMLFormElement>, action: ApplicationExecutionAction) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    void post(`/api/application-workspaces/${encodeURIComponent(workspaceId)}/actions/${encodeURIComponent(action.actionId)}/evidence-proposals`, {
      actorId, idempotencyKey: `fact-${crypto.randomUUID()}`, evidenceType: form.get("evidenceType"),
      evidenceSummary: form.get("evidenceSummary"), evidenceSource: form.get("evidenceSource"), skillLevel: form.get("skillLevel"),
      requirementId: form.get("requirementId"), expectedProfileId: currentId, expectedProfileVersion: currentVersion,
      reviewedCurrentProfile: form.get("reviewed") === "on",
    });
  }
  const disabled = busy || storageError || !!original;
  return <div>
    <p>只有实际产生的新成果才提交。完成准备行动不会自动升级能力；提交提案也不会立即改写职业资料。</p>
    <p>当前核对资料：{currentVersion ? `v${currentVersion}` : "尚未确认"}。请先<Link href="/profile">核对已有事实与技能程度</Link>，避免重复或夸大。</p>
    {original && <aside className="notice" aria-label="待确认事实请求">
      <p>有一个原请求尚待核实。重试沿用原内容和标识，不会在刷新时自动发送。</p>
      <button disabled={busy} onClick={() => void post(original.path, original.body, original)}>重试原事实操作</button>
      {original.rejected && <button disabled={busy} onClick={() => {
        clearWorkspaceFactCommand(window.localStorage, original); setOriginal(null); setError(null);
      }}>服务端已拒绝：丢弃原请求后修正输入</button>}
    </aside>}
    <p className="muted-copy">浏览器会暂存待提交的提案内容用于网络恢复，确认保存后清除。事实仍以服务端已保存记录为准。</p>
    {eligibleActions.map(action => <form key={action.actionId} onSubmit={event => submitProposal(event, action)} className="eligibility-result-card" style={{marginTop: 12}}>
      <strong>为「{action.description}」提交真实成果</strong>
      <p>行动来源：职业资料 v{sources.get(action.actionId)!.profileVersion}；本次由你核对当前资料 v{currentVersion}。</p>
      <label>实际支持的岗位要求<select name="requirementId" required>{sources.get(action.actionId)!.options.map(([id, capability]) => <option key={id} value={id}>{capability} · {id}</option>)}</select></label>
      <label>经历类型<select name="evidenceType" defaultValue="project"><option value="work">工作经历</option><option value="project">项目经历</option><option value="education">教育经历</option><option value="achievement">成果</option><option value="self_report">本人补充</option></select></label>
      <label>真实经历摘要<textarea name="evidenceSummary" required minLength={1} maxLength={2000} /></label>
      <label>证据来源<input name="evidenceSource" required minLength={1} maxLength={1000} placeholder="项目、代码仓库或可核对的工作记录" /></label>
      <label>本人确认的技能程度<select name="skillLevel" defaultValue="unknown"><option value="strong">熟练</option><option value="working">可实际使用</option><option value="basic">基础</option><option value="unknown">暂不判断</option></select></label>
      <p>“暂不判断”会保留已有技能程度，不自动升档或降档。</p>
      <label><input name="reviewed" type="checkbox" required />我已核对当前资料 v{currentVersion}，上述事实、来源和技能程度属实</label>
      <button disabled={disabled || !currentId}>提交待确认事实</button>
    </form>)}
    {context.blockedActionIds.length > 0 && <p>部分行动没有可核对的技能要求来源，不能直接转成技能证据；仍可在职业资料页核实补充事实。</p>}
    {proposals.map(proposal => {
      const baseVersion = proposal.confirmationBaseProfileVersion ?? proposal.sourceProfileVersion;
      const baseId = proposal.confirmationBaseProfileId ?? proposal.sourceProfileId;
      const stale = baseVersion !== currentVersion || baseId !== currentId;
      const root = proposal.originProposalId ?? proposal.proposalId;
      const replaced = proposals.some(item => item.originProposalId === root && item.proposalId !== proposal.proposalId && (item.createdAt > proposal.createdAt || (item.createdAt === proposal.createdAt && item.proposalId > proposal.proposalId)));
      const confirmed = proposals.some(item => (item.proposalId === root || item.originProposalId === root) && item.status === "confirmed");
      return <article className="eligibility-result-card" key={proposal.proposalId} style={{marginTop: 12}}>
        <strong>{proposal.capability}</strong><p>{proposal.evidenceSummary}</p>
        <p>来源：{proposal.evidenceSource} · {proposal.status === "confirmed" ? "已确认" : replaced || confirmed ? "历史提案，不再待处理" : "待确认"}</p>
        <p>行动原始资料 v{proposal.sourceProfileVersion} · 本提案核对基准 v{baseVersion}</p>
        {proposal.sourceAnalysisThreadId && <Link href={`/agent/results/${encodeURIComponent(proposal.sourceAnalysisThreadId)}`}>查看行动创建时的分析与要求</Link>}
        {proposal.status === "pending_confirmation" && !replaced && !confirmed && <>
          {stale ? <form onSubmit={event => {
            event.preventDefault();
            void post(`/api/application-workspaces/${encodeURIComponent(workspaceId)}/evidence-proposals/${encodeURIComponent(proposal.proposalId)}/reconsider`, {
              actorId, idempotencyKey: `reconsider-${crypto.randomUUID()}`, expectedProfileId: currentId,
              expectedProfileVersion: currentVersion, reviewedCurrentProfile: true,
            });
          }}>
            <p>资料已变化，旧提案不能直接确认。重新核对会另存提案，保留这条原始记录，不自动合并事实。</p>
            <label><input type="checkbox" required />我已核对当前资料 v{currentVersion}，上述成果尚未收入且仍然属实</label>
            <button disabled={disabled || !currentId}>按当前资料重新提交待确认提案</button>
          </form> : <button disabled={disabled} onClick={() => void post(`/api/application-workspaces/${encodeURIComponent(workspaceId)}/evidence-proposals/${encodeURIComponent(proposal.proposalId)}/confirm`, {actorId})}>确认这是真实职业事实</button>}
        </>}
        {replaced && <p>已有重新核对提案，请查看较新的记录；这条原文继续保留。</p>}
        {proposal.status === "confirmed" && <p>已新增事实，当前分析需要更新。<Link href={(analysisThreadId ?? proposal.sourceAnalysisThreadId) ? `/agent/results/${encodeURIComponent((analysisThreadId ?? proposal.sourceAnalysisThreadId)!)}/update` : "/agent"}>查看原分析和更新准备</Link>。不承诺排名提高。
          {!(analysisThreadId ?? proposal.sourceAnalysisThreadId) && <button disabled={disabled} onClick={() => void rematch(proposal)}>仅重新匹配此岗位（旧入口，不调用模型）</button>}</p>}
      </article>;
    })}
    {rematchResult && <p className="notice">此岗位重新匹配结果：{rematchResult.previousRecommendation} → {rematchResult.currentRecommendation}；不表示匹配概率。</p>}
    {error && <p role="alert" className="error-copy">{error}</p>}
  </div>;
}

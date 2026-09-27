"use client";

import {FormEvent, useState} from "react";
import {useRouter} from "next/navigation";

import type {ApplicationEvidenceProposal, ApplicationExecutionAction, ApplicationRematchResult} from "@/lib/contracts";

export function ApplicationEvidenceControls({workspaceId, actorId, actions, proposals}: {
  workspaceId: string;
  actorId: string;
  actions: ApplicationExecutionAction[];
  proposals: ApplicationEvidenceProposal[];
}) {
  const router = useRouter();
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ApplicationRematchResult | null>(null);
  const proposalActionIds = new Set(proposals.map((item) => item.actionId));
  const eligibleActions = actions.filter((item) => item.status === "done" && item.sourceRequirementIds.length > 0 && !proposalActionIds.has(item.actionId));

  async function post(path: string, body: object, key: string) {
    setPending(key);
    setError(null);
    try {
      const response = await fetch(path, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
      const payload = await response.json().catch(() => null) as ({detail?: string} & Partial<ApplicationRematchResult>) | null;
      if (!response.ok) throw new Error(payload?.detail ?? "操作未完成，请刷新后重试。");
      if (key.startsWith("rematch-") && payload) setResult(payload as ApplicationRematchResult);
      router.refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "操作未完成，请刷新后重试。");
    } finally {
      setPending(null);
    }
  }

  function submitProposal(event: FormEvent<HTMLFormElement>, action: ApplicationExecutionAction) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    void post(
      `/api/application-workspaces/${encodeURIComponent(workspaceId)}/actions/${encodeURIComponent(action.actionId)}/evidence-proposals`,
      {
        actorId,
        idempotencyKey: `web-evidence-${action.actionId}`,
        evidenceType: form.get("evidenceType"),
        evidenceSummary: form.get("evidenceSummary"),
        evidenceSource: form.get("evidenceSource"),
        skillLevel: form.get("skillLevel"),
      },
      `proposal-${action.actionId}`,
    );
  }

  return <div>
    {eligibleActions.map((action) => <form key={action.actionId} onSubmit={(event) => submitProposal(event, action)} className="eligibility-result-card" style={{marginTop: 12}}>
      <strong>为「{action.sourceGapCapability ?? action.description}」提交真实 Evidence</strong>
      <p className="muted">只填写你真实做过、能说明来源的事实。系统不会根据 Action 完成状态自动推断能力。</p>
      <label>经历类型<select name="evidenceType" defaultValue="project"><option value="work">工作经历</option><option value="project">项目经历</option><option value="education">教育经历</option><option value="achievement">成果</option><option value="self_report">本人补充</option></select></label>
      <label>真实经历摘要<textarea name="evidenceSummary" required minLength={1} maxLength={2000} /></label>
      <label>证据来源<input name="evidenceSource" required minLength={1} maxLength={1000} placeholder="例如：项目名称、代码仓库、工作记录" /></label>
      <label>能力程度<select name="skillLevel" defaultValue="working"><option value="strong">熟练</option><option value="working">可实际使用</option><option value="basic">基础</option><option value="unknown">暂不判断</option></select></label>
      <div className="actions"><button className="button" disabled={pending !== null}>{pending === `proposal-${action.actionId}` ? "正在提交…" : "提交待确认 Evidence"}</button></div>
    </form>)}

    {proposals.map((proposal) => <article className="eligibility-result-card" key={proposal.proposalId} style={{marginTop: 12}}>
      <strong>{proposal.capability}</strong>
      <p>{proposal.evidenceSummary}</p>
      <small className="muted-copy">来源：{proposal.evidenceSource} · 状态：{proposal.status}</small>
      {proposal.status === "pending_confirmation" ? <div className="actions"><button className="button" disabled={pending !== null} onClick={() => post(
        `/api/application-workspaces/${encodeURIComponent(workspaceId)}/evidence-proposals/${encodeURIComponent(proposal.proposalId)}/confirm`,
        {actorId},
        `confirm-${proposal.proposalId}`,
      )}>{pending === `confirm-${proposal.proposalId}` ? "正在确认…" : "确认这是真实职业事实"}</button></div> : null}
      {proposal.status === "confirmed" ? <div className="actions"><button className="button-secondary" disabled={pending !== null} onClick={() => post(
        `/api/application-workspaces/${encodeURIComponent(workspaceId)}/evidence-proposals/${encodeURIComponent(proposal.proposalId)}/rematch`,
        {actorId, idempotencyKey: `web-rematch-${proposal.proposalId}`},
        `rematch-${proposal.proposalId}`,
      )}>{pending === `rematch-${proposal.proposalId}` ? "正在重新验证…" : "用新事实重新验证岗位匹配"}</button></div> : null}
    </article>)}

    {result ? <div className="notice" style={{marginTop: 12}}><strong>重新验证结果：{result.rankingSignal}</strong><p>{result.previousRecommendation} → {result.currentRecommendation}；目标 Requirement 已解除 {result.targetResolvedRequirementIds.length} 项。</p><small>Provider calls: {result.providerCalls}</small></div> : null}
    {error ? <p className="error-copy">{error}</p> : null}
  </div>;
}

"use client";

import {useRef, useState, useTransition} from "react";
import {useRouter} from "next/navigation";

import {WorkspaceRecordBrowser} from "./workspace-record-browser";
import {PendingIndicator} from "./ui/pending-indicator";
import type {ApplicationResumeVariant, ApplicationResumeVariantProposal} from "@/lib/contracts";

export function ApplicationResumeControls({
  workspaceId,
  actorId,
  proposal,
  currentVariant,
  facts,
}: {
  workspaceId: string;
  actorId: string;
  proposal: ApplicationResumeVariantProposal;
  currentVariant: ApplicationResumeVariant | null;
  facts: ReturnType<typeof import("@/lib/preparation-facts").preparationFacts>;
}) {
  const router = useRouter();
  const inFlight = useRef(false);
  const [refreshing, startTransition] = useTransition();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function post(path: string, body: object) {
    if (inFlight.current || refreshing) return;
    inFlight.current = true;
    setPending(true);
    setError(null);
    try {
      const response = await fetch(path, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(body),
      });
      if (!response.ok) throw new Error(response.status === 409
        ? "准备依据或草稿状态有变化；请刷新核对后再决定下一步。"
        : "暂时无法确认岗位简历是否保存；请刷新查看当前状态。");
      startTransition(() => router.refresh());
    } catch (caught) {
      setError(caught instanceof TypeError ? "连接中断，请刷新查看当前状态；页面不会自动重试。"
        : caught instanceof Error ? caught.message : "岗位简历操作未确认，请刷新核对。");
    } finally {
      inFlight.current = false;
      setPending(false);
    }
  }

  const canSave = proposal.highlights.length > 0 && currentVariant === null;
  const canReview = currentVariant?.status === "draft";

  const busy = pending || refreshing;
  return <div style={{marginTop: 12}} aria-busy={busy}>
    {proposal.highlights.length > 0 ? <WorkspaceRecordBrowser label="简历要点列表" records={proposal.highlights.map(item => ({
      id: item.requirementId,
      title: item.capability,
      summary: `${item.evidenceIds.length} 条已确认经历`,
      content: <div className="stack-md">
        <h3>{item.capability}</h3>
        <p>建议把这段已确认的经历放在简历里，与对应的岗位要求一起核对。不会补写未确认的成果。</p>
        <details><summary>查看依据 · 岗位原文与经历</summary>
          <p>{facts.requirements.get(item.requirementId)?.text ?? "已关联岗位要求；可到准备依据核对原文。"}</p>
          <p>{item.evidenceIds.map(id => facts.evidenceSummaries.get(id)).filter(Boolean).join("；") ||
            `有 ${item.evidenceIds.length} 条已确认经历作为依据；此处未提供可展示的摘要。`}</p>
        </details>
      </div>,
    }))} /> : <div className="jl-callout"><p>目前没有能写入岗位简历的已确认经历。请核对岗位依据，或补充真实经历。</p></div>}
    {proposal.unresolvedRequirementIds.length > 0 ? <p className="muted">仍有 {proposal.unresolvedRequirementIds.length} 项岗位要求还缺可引用的真实经历；这些缺口不会被简历改写掩盖。</p> : null}
    {currentVariant ? <p role="status">当前岗位简历状态：<strong>{currentVariant.status === "reviewed" ? "已人工审核" : "草稿待审核"}</strong></p> : <p className="muted">尚未保存岗位专用简历版本。</p>}
    <div className="actions">
      {canSave ? <button className="button-secondary" disabled={busy} onClick={() => post(
        `/api/application-workspaces/${encodeURIComponent(workspaceId)}/resume-variants`,
        {actorId, idempotencyKey: `web-resume-variant-${workspaceId}`},
      )}>{busy ? "正在保存…" : "保存岗位简历草稿"}</button> : null}
      {canReview && currentVariant ? <button className="button" disabled={busy} onClick={() => post(
        `/api/application-workspaces/${encodeURIComponent(workspaceId)}/resume-variants/${encodeURIComponent(currentVariant.variantId)}/review`,
        {actorId, expectedStatus: "draft"},
      )}>{busy ? "正在确认…" : "确认已人工审核"}</button> : null}
    </div>
    {busy && <PendingIndicator label="正在处理本次简历请求…" />}
    {error ? <p role="alert" className="error-copy">{error}</p> : null}
  </div>;
}

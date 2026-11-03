"use client";

import {useState} from "react";
import {useRouter} from "next/navigation";

import type {ApplicationResumeVariant, ApplicationResumeVariantProposal} from "@/lib/contracts";

export function ApplicationResumeControls({
  workspaceId,
  actorId,
  proposal,
  currentVariant,
}: {
  workspaceId: string;
  actorId: string;
  proposal: ApplicationResumeVariantProposal;
  currentVariant: ApplicationResumeVariant | null;
}) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function post(path: string, body: object) {
    setPending(true);
    setError(null);
    try {
      const response = await fetch(path, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(body),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null) as {detail?: string} | null;
        throw new Error(payload?.detail ?? "岗位简历操作失败，请刷新后重试。");
      }
      router.refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "岗位简历操作失败，请刷新后重试。");
    } finally {
      setPending(false);
    }
  }

  const canSave = proposal.highlights.length > 0 && currentVariant === null;
  const canReview = currentVariant?.status === "draft";

  return <div style={{marginTop: 12}}>
    <div className="eligibility-groups">
      {proposal.highlights.map((item) => <article className="eligibility-result-card" key={item.requirementId}>
        <strong>{item.capability}</strong>
        <p>Requirement：{item.requirementId}</p>
        <small className="muted-copy">已确认 Evidence：{item.evidenceIds.join("、")}</small>
      </article>)}
    </div>
    {proposal.unresolvedRequirementIds.length > 0 ? <p className="muted">仍有 {proposal.unresolvedRequirementIds.length} 项 Requirement 没有可用 Evidence；这些缺口不会被简历改写掩盖。</p> : null}
    {currentVariant ? <p>当前岗位简历状态：<strong>{currentVariant.status === "reviewed" ? "已人工审核" : "草稿待审核"}</strong></p> : <p className="muted">尚未保存岗位专用简历版本。</p>}
    <div className="actions">
      {canSave ? <button className="button-secondary" disabled={pending} onClick={() => post(
        `/api/application-workspaces/${encodeURIComponent(workspaceId)}/resume-variants`,
        {actorId, idempotencyKey: `web-resume-variant-${workspaceId}`},
      )}>{pending ? "正在保存…" : "保存岗位简历草稿"}</button> : null}
      {canReview && currentVariant ? <button className="button" disabled={pending} onClick={() => post(
        `/api/application-workspaces/${encodeURIComponent(workspaceId)}/resume-variants/${encodeURIComponent(currentVariant.variantId)}/review`,
        {actorId, expectedStatus: "draft"},
      )}>{pending ? "正在确认…" : "确认已人工审核"}</button> : null}
    </div>
    {error ? <p className="error-copy">{error}</p> : null}
  </div>;
}

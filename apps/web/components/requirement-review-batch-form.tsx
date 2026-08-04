"use client";

import {useRouter} from "next/navigation";
import {useMemo, useState} from "react";

import type {
  ApiErrorBody,
  RequirementReviewBatchDetail,
  RequirementReviewCandidate,
} from "@/lib/contracts";
import {
  canSelectRequirementCandidate,
  requirementReviewCohortKey,
} from "@/lib/requirement-reviews";

export function RequirementReviewBatchForm({
  candidates,
}: {
  candidates: RequirementReviewCandidate[];
}) {
  const router = useRouter();
  const [title, setTitle] = useState("Requirement 真实岗位人工验收");
  const [reviewer, setReviewer] = useState("local-user");
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selected = useMemo(
    () => candidates.filter((item) => selectedIds.includes(item.extractionId)),
    [candidates, selectedIds],
  );
  const selectedCohort = selected[0]
    ? requirementReviewCohortKey(selected[0])
    : null;

  function toggle(candidate: RequirementReviewCandidate) {
    setError(null);
    setSelectedIds((current) => {
      if (current.includes(candidate.extractionId)) {
        return current.filter((item) => item !== candidate.extractionId);
      }
      const currentCandidates = candidates.filter((item) => current.includes(item.extractionId));
      if (!canSelectRequirementCandidate(candidate, currentCandidates)) return current;
      return [...current, candidate.extractionId];
    });
  }

  async function submit() {
    setError(null);
    if (selectedIds.length === 0) {
      setError("至少选择一个已抽取岗位。正式人工证据需要 20 个。" );
      return;
    }
    setPending(true);
    try {
      const response = await fetch("/api/requirement-review-batches", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({title, reviewer, extractionIds: selectedIds}),
      });
      if (!response.ok) {
        const body = (await response.json()) as Partial<ApiErrorBody>;
        throw new Error(body.error?.message ?? `创建批次失败（${response.status}）。`);
      }
      const detail = (await response.json()) as RequirementReviewBatchDetail;
      router.push(`/evals/requirements/manual/${encodeURIComponent(detail.summary.id)}`);
      router.refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "创建人工验收批次失败。" );
    } finally {
      setPending(false);
    }
  }

  if (candidates.length === 0) {
    return (
      <p className="notice">
        当前没有可审查的 Requirement Extraction。请先导入岗位并在岗位详情中执行要求抽取。
      </p>
    );
  }

  return (
    <div className="review-form">
      <div className="form-grid">
        <label>
          批次名称
          <input value={title} onChange={(event) => setTitle(event.target.value)} required />
        </label>
        <label>
          审查人
          <input value={reviewer} onChange={(event) => setReviewer(event.target.value)} required />
        </label>
      </div>

      <div className="section-heading-row">
        <div>
          <h3>选择同一模型版本的岗位</h3>
          <p className="muted">
            已选 {selectedIds.length}/20。选择第一条后，其他 Cohort 会被禁用。
          </p>
        </div>
        {selectedCohort ? <span className="code">{selectedCohort}</span> : null}
      </div>

      <div className="eval-run-list">
        {candidates.map((candidate) => {
          const checked = selectedIds.includes(candidate.extractionId);
          const allowed = canSelectRequirementCandidate(candidate, selected);
          return (
            <label className="eval-run-card" key={candidate.extractionId}>
              <div className="eval-run-card-heading">
                <span>
                  <input
                    type="checkbox"
                    checked={checked}
                    disabled={!allowed}
                    onChange={() => toggle(candidate)}
                  />{" "}
                  {candidate.title} · {candidate.company}
                </span>
                <span>{candidate.requirementCount} 条要求</span>
              </div>
              <p className="code">{candidate.extractionId}</p>
              <div className="meta-list compact-meta">
                <div><span className="meta-label">Provider / Model</span><strong>{candidate.provider} / {candidate.model}</strong></div>
                <div><span className="meta-label">Extractor / Prompt</span><strong>{candidate.extractorVersion} / {candidate.promptVersion}</strong></div>
                <div><span className="meta-label">Trace</span><strong className="code">{candidate.traceRunId}</strong></div>
              </div>
            </label>
          );
        })}
      </div>

      {error ? <div className="inline-error">{error}</div> : null}
      <div className="actions">
        <button
          className="button"
          type="button"
          disabled={pending || selectedIds.length === 0}
          onClick={() => void submit()}
        >
          {pending ? "创建中…" : `创建 ${selectedIds.length} 条验收批次`}
        </button>
      </div>
    </div>
  );
}

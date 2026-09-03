import Link from "next/link";

import {RequirementReviewBatchForm} from "@/components/requirement-review-batch-form";
import {ServiceError} from "@/components/service-error";
import {
  BackendApiError,
  fetchRequirementReviewBatches,
  fetchRequirementReviewCandidates,
} from "@/lib/backend";
import {formatDateTime} from "@/lib/format";
import {
  buildRequirementReviewFormalReadiness,
  requirementReviewEvidenceLabel,
} from "@/lib/requirement-reviews";

export const dynamic = "force-dynamic";

export default async function RequirementManualReviewPage() {
  let candidates;
  let batches;
  try {
    [candidates, batches] = await Promise.all([
      fetchRequirementReviewCandidates(),
      fetchRequirementReviewBatches(),
    ]);
  } catch (caught) {
    const message =
      caught instanceof BackendApiError
        ? caught.message
        : "读取 Requirement 人工验收数据时发生未知错误。";
    return <ServiceError message={message} />;
  }

  const formalReadiness = buildRequirementReviewFormalReadiness(candidates.items);
  const targetCandidate = formalReadiness.targetCandidates[0] ?? null;

  return (
    <>
      <section className="page-heading">
        <p className="eyebrow">Requirement Manual Quality Evidence</p>
        <h1>真实岗位人工验收批次</h1>
        <p className="lede">
          选择同一 Provider、Model、Extractor 和 Prompt 的具体 Extraction 版本，逐岗位对照完整 JD、Requirements 与 Trace。系统不会替你生成人工判断。
        </p>
        <div className="actions">
          <Link className="button" href="/evals/requirements/canary">
            打开 Canary 人工放行
          </Link>
          <Link className="button-ghost" href="/evals/requirements">
            返回自动 Eval 治理
          </Link>
        </div>
      </section>

      <section className="detail-card">
        <div className="section-heading-row">
          <div>
            <h2>正式验收准备状态</h2>
            <p className="muted">
              正式 Match baseline 必须由同一 Provider、Model、Extractor 和 Prompt 的 20 个 current Extraction 组成；候选总数达到 20 并不代表已经能创建正式批次。
            </p>
          </div>
          <span className={`status-chip ${formalReadiness.formalReady ? "status-pass" : "status-fixture"}`}>
            {formalReadiness.formalReady ? "20/20 可正式验收" : `${formalReadiness.targetCandidates.length}/20 同一版本`}
          </span>
        </div>

        <div className="summary-grid eval-summary-grid">
          <div className="summary-card"><span>Current 候选</span><strong>{candidates.total}</strong></div>
          <div className="summary-card"><span>最大一致 Cohort</span><strong>{formalReadiness.targetCandidates.length}/20</strong></div>
          <div className="summary-card"><span>版本 Cohort</span><strong>{formalReadiness.cohortCount}</strong></div>
          <div className="summary-card"><span>需要统一</span><strong>{formalReadiness.outlierCandidates.length}</strong></div>
        </div>

        {formalReadiness.formalReady ? (
          <div className="review-result review-accepted">
            <strong>正式 20-case Requirement Review 已准备好</strong>
            <p>下面可以一键选择这 20 个完全一致的 current Extraction，创建正式人工验收批次。创建批次不会调用 Provider，也不会替你做人工 Accept / Reject。</p>
          </div>
        ) : (
          <div className="review-result review-pending">
            <strong>当前还不能创建正式 20-case baseline</strong>
            <p>
              当前 {candidates.total} 个 current Extraction 被拆成 {formalReadiness.cohortCount} 个模型版本组；最大一致组只有 {formalReadiness.targetCandidates.length}/20。
              先把下面 {formalReadiness.outlierCandidates.length} 个岗位重新分析到同一当前版本，再回来创建正式批次。不要用 {formalReadiness.targetCandidates.length} 条练习批次代替正式质量证据。
            </p>
            {targetCandidate ? (
              <p className="code">目标一致版本：{formalReadiness.targetCohortKey}</p>
            ) : null}
            {formalReadiness.outlierCandidates.length > 0 ? (
              <div className="eval-run-list">
                {formalReadiness.outlierCandidates.map((candidate) => (
                  <article className="eval-run-card" key={candidate.extractionId}>
                    <strong>{candidate.title} · {candidate.company}</strong>
                    <p className="muted">当前模型：{candidate.model}</p>
                    <div className="actions">
                      <Link className="button-ghost" href={`/jobs/${candidate.jobId}`}>
                        打开岗位并重新分析 →
                      </Link>
                    </div>
                  </article>
                ))}
              </div>
            ) : null}
          </div>
        )}
      </section>

      <section className="detail-card">
        <div className="section-heading-row">
          <div>
            <h2>创建版本冻结的审查批次</h2>
            <p className="muted">
              当前有 {candidates.total} 个带最新 Requirement Extraction 的岗位。1～19 条仍可作为练习批次；只有上方状态达到 20/20 才能形成正式人工质量证据。
            </p>
          </div>
        </div>
        <RequirementReviewBatchForm
          candidates={candidates.items}
          formalCandidateIds={formalReadiness.formalReady ? formalReadiness.targetCandidates.map((item) => item.extractionId) : []}
        />
      </section>

      <section className="detail-card">
        <div className="section-heading-row">
          <div>
            <h2>批次历史</h2>
            <p className="muted">共 {batches.total} 个不可变批次</p>
          </div>
        </div>
        {batches.items.length === 0 ? (
          <p className="notice">尚无人工验收批次。</p>
        ) : (
          <div className="eval-run-list">
            {batches.items.map((batch) => (
              <article className="eval-run-card" key={batch.id}>
                <div className="eval-run-card-heading">
                  <div>
                    <span className={`status-chip ${batch.completed ? "status-pass" : "status-fixture"}`}>
                      {batch.completed ? "已审完" : "进行中"}
                    </span>
                    <span className={`status-chip ${batch.formalEvidenceEligible ? "status-live" : batch.staleCaseCount > 0 ? "status-fail" : "status-fixture"}`}>
                      {requirementReviewEvidenceLabel(batch)}
                    </span>
                  </div>
                  <time>{formatDateTime(batch.createdAt)}</time>
                </div>
                <h3>{batch.title}</h3>
                <p className="code">{batch.id}</p>
                <div className="summary-grid eval-summary-grid">
                  <div className="summary-card"><span>进度</span><strong>{batch.reviewedCount}/{batch.sampleSize}</strong></div>
                  <div className="summary-card"><span>Accepted</span><strong>{batch.acceptedCount}</strong></div>
                  <div className="summary-card"><span>Rejected</span><strong>{batch.rejectedCount}</strong></div>
                  <div className="summary-card"><span>Stale</span><strong>{batch.staleCaseCount}</strong></div>
                </div>
                <div className="meta-list compact-meta">
                  <div><span className="meta-label">Reviewer</span><strong>{batch.reviewer}</strong></div>
                  <div><span className="meta-label">Provider / Model</span><strong>{batch.provider} / {batch.model}</strong></div>
                  <div><span className="meta-label">Extractor / Prompt</span><strong>{batch.extractorVersion} / {batch.promptVersion}</strong></div>
                </div>
                <div className="actions">
                  <Link className="button" href={`/evals/requirements/manual/${batch.id}`}>
                    打开逐岗位验收
                  </Link>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>
    </>
  );
}

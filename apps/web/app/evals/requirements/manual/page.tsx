import {MaintenanceHeading} from "@/components/maintenance-heading";
import Link from "next/link";
import {Pagination} from "@/components/ui/pagination";
import {parsePageOffset, readKnownPage} from "@/lib/pagination";

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

export default async function RequirementManualReviewPage({searchParams}: {searchParams: Promise<{offset?: string | string[]}>}) {
  const requestedOffset = parsePageOffset((await searchParams).offset);
  const limit = 20;
  let offset = requestedOffset;
  let adjusted = false;
  let candidates;
  let batches;
  try {
    [candidates, batches] = await Promise.all([
      fetchRequirementReviewCandidates(),
      readKnownPage(requestedOffset, limit, next => fetchRequirementReviewBatches(limit, next)).then(result => {
        offset = result.offset; adjusted = result.adjusted; return result.page;
      }),
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
      <MaintenanceHeading title="岗位要求人工验收" returnTo="jobs"
        description="对照岗位原文，检查模型是否漏读、误读或补写了要求。验收由维护者逐条完成，和求职者核对自己的岗位不是同一件事。">
        <Link className="button-ghost" href="/evals/requirements/canary">查看在线小批验证</Link>
        <Link className="button-ghost" href="/evals/requirements">返回岗位要求评测</Link>
      </MaintenanceHeading>

      <section className="detail-card">
        <div className="section-heading-row">
          <div>
            <h2>正式验收准备状态</h2>
            <p className="muted">
              建立正式验收批次需要 20 条当前有效、分析配置一致的岗位结果。以下只统计本页已载入的候选。
            </p>
          </div>
          <span className={`status-chip ${formalReadiness.formalReady ? "status-pass" : "status-fixture"}`}>
            {formalReadiness.formalReady ? `${formalReadiness.targetCandidates.length} 条同版本候选` : `${formalReadiness.targetCandidates.length}/20 同一版本`}
          </span>
        </div>

        <div className="summary-grid eval-summary-grid">
          <div className="summary-card"><span>当前有效候选</span><strong>{candidates.total}</strong></div>
          <div className="summary-card"><span>最多的同配置候选</span><strong>{formalReadiness.targetCandidates.length} 条</strong></div>
          <div className="summary-card"><span>配置组数</span><strong>{formalReadiness.cohortCount}</strong></div>
          <div className="summary-card"><span>其他版本</span><strong>{formalReadiness.outlierCandidates.length}</strong></div>
        </div>

        {formalReadiness.formalReady ? (
          <div className="review-result review-accepted">
            <strong>已可选取 20 条同版本候选</strong>
            <p>下面可以从同一版本的候选中一键选择 20 个，创建人工验收批次。创建批次不会调用在线模型，也不会替你做人工判断；正式资格仍由服务端检查。</p>
          </div>
        ) : (
          <div className="review-result review-pending">
            <strong>还没有凑齐 20 条同配置的候选</strong>
            <p>
              本页加载的 {candidates.items.length} 个候选被拆成 {formalReadiness.cohortCount} 个模型版本组；最大一致组有 {formalReadiness.targetCandidates.length}/20。
              请检查候选岗位和分析版本，确定如何补足同一版本的审核样本。当前离线分析不能保证生成目标版本；重新分析也可能使已有审核样本失效。不要用 {formalReadiness.targetCandidates.length} 条练习批次代替正式质量证据。
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
                    <p className="muted">请先核对该岗位及其分析版本；不要为凑齐样本而覆盖已有结果。</p>
                    <div className="actions">
                      <Link className="button-ghost" href={`/jobs/${candidate.jobId}`}>
                        先查看岗位详情 →
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
            <h2>创建人工验收批次</h2>
            <p className="muted">
              共找到 {candidates.total} 个候选，本页加载 {candidates.items.length} 个。1～19 条可作为练习批次；20 条只是正式证据的必要条件之一。
            </p>
          </div>
        </div>
        <RequirementReviewBatchForm
          candidates={candidates.items}
            formalCandidateIds={formalReadiness.formalReady ? formalReadiness.targetCandidates.slice(0, 20).map((item) => item.extractionId) : []}
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
        {adjusted && <p role="status" className="jl-callout">列表已更新，已显示最后一个有效页面。</p>}
        <Pagination label="质量记录分页" offset={offset} limit={limit} count={batches.items.length} total={batches.total}
          href={next => next === 0 ? "/evals/requirements/manual" : `/evals/requirements/manual?offset=${next}`} />
      </section>
    </>
  );
}

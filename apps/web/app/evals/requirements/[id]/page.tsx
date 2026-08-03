import Link from "next/link";
import {notFound} from "next/navigation";

import {RequirementEvalReviewForm} from "@/components/requirement-eval-review-form";
import {ServiceError} from "@/components/service-error";
import {BackendApiError, fetchRequirementEvalRun} from "@/lib/backend";
import {formatDateTime} from "@/lib/format";
import {
  formatDelta,
  formatRate,
  sortRequirementEvalCases,
} from "@/lib/requirement-evals";

export const dynamic = "force-dynamic";

export default async function RequirementEvalRunDetailPage({
  params,
}: {
  params: Promise<{id: string}>;
}) {
  const {id} = await params;
  let detail;
  try {
    detail = await fetchRequirementEvalRun(id);
  } catch (caught) {
    if (caught instanceof BackendApiError && caught.status === 404) notFound();
    const message =
      caught instanceof BackendApiError
        ? caught.message
        : "读取 Requirement Eval 详情时发生未知错误。";
    return <ServiceError message={message} />;
  }

  const cases = sortRequirementEvalCases(detail.cases);
  const failedCount = cases.filter((item) => !item.passed).length;

  return (
    <>
      <section className="page-heading">
        <p className="eyebrow">Requirement Eval Review</p>
        <h1>逐案例审查</h1>
        <p className="lede">
          优先审查失败案例、importance 错误和 Trace。技术 Gate 通过只代表允许进入人工审核，不等于已经成为正式 baseline。
        </p>
        <p className="code">{detail.summary.id}</p>
      </section>

      <div className="summary-grid">
        <div className="summary-card"><span>Mode</span><strong>{detail.summary.mode}</strong></div>
        <div className="summary-card"><span>Gate</span><strong>{detail.summary.gatePassed ? "通过" : "失败"}</strong></div>
        <div className="summary-card"><span>Case</span><strong>{detail.summary.passedCases}/{detail.summary.totalCases}</strong></div>
        <div className="summary-card"><span>失败案例</span><strong>{failedCount}</strong></div>
      </div>

      <section className="detail-grid">
        <article className="detail-card">
          <h2>案例结果</h2>
          {cases.map((item) => (
            <section className={`eval-case ${item.passed ? "eval-case-pass" : "eval-case-fail"}`} key={item.caseId}>
              <div className="eval-case-heading">
                <div>
                  <span className={`status-chip ${item.passed ? "status-pass" : "status-fail"}`}>
                    {item.passed ? "通过" : "失败"}
                  </span>
                  <strong>{item.caseId}</strong>
                </div>
                <span className="code">{item.traceRunId ?? "无 Trace"}</span>
              </div>
              {item.error ? <p className="inline-error">{item.error}</p> : null}
              <div className="case-grid">
                <div><span className="meta-label">缺失要求</span><strong>{item.missingRequirements.join("、") || "无"}</strong></div>
                <div><span className="meta-label">Importance 错误</span><strong>{item.wrongImportance.join("、") || "无"}</strong></div>
                <div><span className="meta-label">禁止能力</span><strong>{item.observedForbiddenCapabilities.join("、") || "无"}</strong></div>
                <div><span className="meta-label">实际要求数</span><strong>{item.actualRequirements.length}</strong></div>
              </div>
              {item.actualRequirements.length > 0 ? (
                <details className="detail-section">
                  <summary>查看实际结构化要求</summary>
                  <ul>
                    {item.actualRequirements.map((requirement) => (
                      <li className="code" key={requirement}>{requirement}</li>
                    ))}
                  </ul>
                </details>
              ) : null}
            </section>
          ))}
        </article>

        <aside className="detail-card">
          <h2>运行上下文</h2>
          <div className="meta-list">
            <div><span className="meta-label">Provider / Model</span><strong>{detail.summary.provider} / {detail.summary.model}</strong></div>
            <div><span className="meta-label">Extractor / Prompt</span><strong>{detail.summary.extractorVersion} / {detail.summary.promptVersion}</strong></div>
            <div><span className="meta-label">Gate</span><strong>{detail.summary.gateVersion}</strong></div>
            <div><span className="meta-label">运行时间</span><strong>{formatDateTime(detail.summary.createdAt)}</strong></div>
          </div>

          <section className="detail-section">
            <h3>质量指标</h3>
            <div className="meta-list">
              <div><span className="meta-label">Case 通过率</span><strong>{formatRate(detail.summary.casePassRate)}</strong></div>
              <div><span className="meta-label">Workflow 成功率</span><strong>{formatRate(detail.summary.workflowSuccessRate)}</strong></div>
              <div><span className="meta-label">能力召回</span><strong>{formatRate(detail.summary.capabilityRecall)}</strong></div>
              <div><span className="meta-label">Importance 准确率</span><strong>{formatRate(detail.summary.importanceAccuracy)}</strong></div>
              <div><span className="meta-label">禁止能力率</span><strong>{formatRate(detail.summary.forbiddenCapabilityRate)}</strong></div>
            </div>
          </section>

          {detail.comparison ? (
            <section className="detail-section">
              <h3>Baseline 差异</h3>
              <p className="code">{detail.comparison.baselineRunId}</p>
              <div className="meta-list">
                <div><span className="meta-label">Case</span><strong>{formatDelta(detail.comparison.casePassRateDelta)}</strong></div>
                <div><span className="meta-label">能力召回</span><strong>{formatDelta(detail.comparison.capabilityRecallDelta)}</strong></div>
                <div><span className="meta-label">Importance</span><strong>{formatDelta(detail.comparison.importanceAccuracyDelta)}</strong></div>
                <div><span className="meta-label">禁止能力率</span><strong>{formatDelta(detail.comparison.forbiddenCapabilityRateDelta)}</strong></div>
              </div>
            </section>
          ) : null}

          <section className="detail-section">
            <h3>人工 Review</h3>
            {detail.review ? (
              <div className={`review-result review-${detail.review.decision}`}>
                <strong>{detail.review.decision}</strong>
                <p>{detail.review.notes}</p>
                <small>{detail.review.reviewer} · {formatDateTime(detail.review.reviewedAt)}</small>
              </div>
            ) : (
              <RequirementEvalReviewForm
                run={detail.summary}
                alreadyReviewed={false}
              />
            )}
          </section>

          <div className="actions">
            <Link className="button-ghost" href="/evals/requirements">返回运行历史</Link>
          </div>
        </aside>
      </section>
    </>
  );
}

import Link from "next/link";
import {notFound} from "next/navigation";

import {ProfileEvalReviewForm} from "@/components/profile-eval-review-form";
import {ServiceError} from "@/components/service-error";
import {BackendApiError, fetchProfileEvalRun} from "@/lib/backend";
import {formatDateTime} from "@/lib/format";
import {formatDelta, formatRate, sortProfileEvalCases} from "@/lib/profile-evals";

export const dynamic = "force-dynamic";

export default async function ProfileEvalRunDetailPage({
  params,
}: {
  params: Promise<{id: string}>;
}) {
  const {id} = await params;
  let detail;
  try {
    detail = await fetchProfileEvalRun(id);
  } catch (caught) {
    if (caught instanceof BackendApiError && caught.status === 404) notFound();
    const message =
      caught instanceof BackendApiError
        ? caught.message
        : "读取 Profile Eval 详情时发生未知错误。";
    return <ServiceError message={message} />;
  }

  const cases = sortProfileEvalCases(detail.cases);
  const failedCount = cases.filter((item) => !item.passed).length;

  return (
    <>
      <section className="page-heading">
        <p className="eyebrow">Profile Eval Review</p>
        <h1>逐案例审查</h1>
        <p className="lede">
          先看失败案例和 Trace，再决定接受或拒绝。技术 Gate 通过只代表允许进入人工审核，不等于已经批准。
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
              {item.failureReasons.length > 0 ? (
                <div className="inline-error">
                  {item.failureReasons.map((reason) => <p key={reason}>{reason}</p>)}
                </div>
              ) : null}
              <div className="case-grid">
                <div><span className="meta-label">期望技能</span><strong>{item.expectedSkills.join("、") || "—"}</strong></div>
                <div><span className="meta-label">实际技能</span><strong>{item.actualSkills.join("、") || "—"}</strong></div>
                <div><span className="meta-label">缺失技能</span><strong>{item.missingSkills.join("、") || "无"}</strong></div>
                <div><span className="meta-label">年限</span><strong>{item.expectedYears ?? "—"} → {item.actualYears ?? "—"}</strong></div>
              </div>
              {item.observedForbiddenTerms.length > 0 ? (
                <p className="inline-error">出现禁止事实：{item.observedForbiddenTerms.join("、")}</p>
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
              <div><span className="meta-label">技能召回</span><strong>{formatRate(detail.summary.skillRecall)}</strong></div>
              <div><span className="meta-label">年限准确率</span><strong>{formatRate(detail.summary.yearsAccuracy)}</strong></div>
              <div><span className="meta-label">禁用事实率</span><strong>{formatRate(detail.summary.forbiddenFactRate)}</strong></div>
            </div>
          </section>

          {detail.comparison ? (
            <section className="detail-section">
              <h3>Baseline 差异</h3>
              <p className="code">{detail.comparison.baselineRunId}</p>
              <div className="meta-list">
                <div><span className="meta-label">Case</span><strong>{formatDelta(detail.comparison.casePassRateDelta)}</strong></div>
                <div><span className="meta-label">技能召回</span><strong>{formatDelta(detail.comparison.skillRecallDelta)}</strong></div>
                <div><span className="meta-label">禁用事实率</span><strong>{formatDelta(detail.comparison.forbiddenFactRateDelta)}</strong></div>
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
              <ProfileEvalReviewForm run={detail.summary} alreadyReviewed={false} />
            )}
          </section>

          <div className="actions">
            <Link className="button-ghost" href="/evals/profile">返回运行历史</Link>
          </div>
        </aside>
      </section>
    </>
  );
}

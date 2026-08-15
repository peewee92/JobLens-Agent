import Link from "next/link";
import {notFound} from "next/navigation";

import {RequirementCaseReviewForm} from "@/components/requirement-case-review-form";
import {RequirementReviewFinalDecisionForm} from "@/components/requirement-review-final-decision-form";
import {ServiceError} from "@/components/service-error";
import {BackendApiError, fetchRequirementReviewBatch} from "@/lib/backend";
import {formatDateTime} from "@/lib/format";
import {
  requirementImportanceLabel,
  requirementTypeLabel,
  sortJobRequirements,
} from "@/lib/job-requirements";
import {
  requirementReviewEvidenceLabel,
  requirementReviewFinalDecisionLabel,
  requirementReviewIssueLabels,
  requirementReviewMatchGateLabel,
  sortRequirementReviewCases,
} from "@/lib/requirement-reviews";

export const dynamic = "force-dynamic";

export default async function RequirementManualReviewDetailPage({
  params,
}: {
  params: Promise<{id: string}>;
}) {
  const {id} = await params;
  let detail;
  try {
    detail = await fetchRequirementReviewBatch(id);
  } catch (caught) {
    if (caught instanceof BackendApiError && caught.status === 404) notFound();
    const message =
      caught instanceof BackendApiError
        ? caught.message
        : "读取 Requirement 人工验收批次时发生未知错误。";
    return <ServiceError message={message} />;
  }

  const cases = sortRequirementReviewCases(detail.cases);
  const evidenceLabel = requirementReviewEvidenceLabel(detail.summary);
  const matchGateLabel = requirementReviewMatchGateLabel(detail.summary);

  return (
    <>
      <section className="page-heading">
        <p className="eyebrow">Requirement Manual Review</p>
        <h1>{detail.summary.title}</h1>
        <p className="lede">
          每个 Case 都绑定一个不可变 Extraction。请亲自比较完整 JD、Requirement 类型、importance、归一化能力和 evidenceSpan；不要让 Agent 替你给出 accepted/rejected。
        </p>
        <p className="code">{detail.summary.id}</p>
        <div className="actions">
          <Link className="button-ghost" href="/evals/requirements/manual">
            返回批次列表
          </Link>
        </div>
      </section>

      <div className="summary-grid">
        <div className="summary-card"><span>进度</span><strong>{detail.summary.reviewedCount}/{detail.summary.sampleSize}</strong></div>
        <div className="summary-card"><span>Accepted</span><strong>{detail.summary.acceptedCount}</strong></div>
        <div className="summary-card"><span>Rejected</span><strong>{detail.summary.rejectedCount}</strong></div>
        <div className="summary-card"><span>Stale</span><strong>{detail.summary.staleCaseCount}</strong></div>
        <div className="summary-card"><span>Match Gate</span><strong>{detail.summary.matchReleaseEligible ? "Allowed" : "Blocked"}</strong></div>
      </div>

      <section className="detail-grid">
        <article className="detail-card">
          <div className="section-heading-row">
            <div>
              <h2>逐岗位验收</h2>
              <p className="muted">Case 按 #1～#20 固定顺序显示；提交判断后会留在原位置并显示已保存结果。</p>
            </div>
            <span className={`status-chip ${detail.summary.formalEvidenceEligible ? "status-live" : detail.summary.staleCaseCount > 0 ? "status-fail" : "status-fixture"}`}>
              {evidenceLabel}
            </span>
          </div>

          {cases.map((item) => {
            const requirements = sortJobRequirements(item.requirements);
            const mustHaveCount = requirements.filter((item) => item.importance === "must_have").length;
            const preferredCount = requirements.filter((item) => item.importance === "preferred").length;
            const bonusCount = requirements.filter((item) => item.importance === "bonus").length;
            return (
              <section
                className={`eval-case ${item.review?.decision === "rejected" ? "eval-case-fail" : item.review ? "eval-case-pass" : ""}`}
                key={item.id}
              >
                <div className="eval-case-heading">
                  <div>
                    <span className={`status-chip ${item.isCurrent ? "status-pass" : "status-fail"}`}>
                      {item.isCurrent ? "当前版本" : "已过期版本"}
                    </span>
                    <strong>#{item.caseIndex + 1} {item.title} · {item.company}</strong>
                  </div>
                  <span className="code">{item.extractionId}</span>
                </div>

                <div className="meta-list compact-meta">
                  <div><span className="meta-label">Job ID</span><strong className="code">{item.jobId}</strong></div>
                  <div><span className="meta-label">Trace</span><strong className="code">{item.traceRunId}</strong></div>
                  <div><span className="meta-label">Provider / Model</span><strong>{item.provider} / {item.model}</strong></div>
                  <div><span className="meta-label">抽取时间</span><strong>{formatDateTime(item.createdAt)}</strong></div>
                </div>

                <section className="detail-section">
                  <h3>完整 JD</h3>
                  <p style={{whiteSpace: "pre-wrap"}}>{item.description ?? "该岗位没有可用 JD 文本。"}</p>
                </section>

                <section className="detail-section">
                  <details className="requirement-review-requirements">
                    <summary>
                      <span>
                        <strong>查看抽取出的 Requirements（{requirements.length}）</strong>
                        <small>点击展开逐条核对，核对完成后可再次收起。</small>
                      </span>
                      <span className="requirement-review-counts" aria-label="Requirement 重要性分布">
                        必须 {mustHaveCount} · 优先 {preferredCount} · 加分 {bonusCount}
                      </span>
                    </summary>
                    <div className="eval-run-list requirement-review-requirement-list">
                      {requirements.map((requirement) => (
                        <article className="eval-run-card" key={requirement.id}>
                          <div className="eval-run-card-heading">
                            <div>
                              <span className={`status-chip status-${requirement.importance === "must_have" ? "fail" : requirement.importance === "preferred" ? "live" : "fixture"}`}>
                                {requirementImportanceLabel(requirement.importance)}
                              </span>
                              <span className="status-chip status-fixture">
                                {requirementTypeLabel(requirement.type)}
                              </span>
                            </div>
                            <span>{Math.round(requirement.confidence * 100)}%</span>
                          </div>
                          <strong>{requirement.originalText}</strong>
                          <p>归一化能力：{requirement.normalizedCapability ?? "—"}</p>
                          <p className="notice">Evidence：{requirement.evidenceSpan}</p>
                          <p className="code">{requirement.id}</p>
                        </article>
                      ))}
                    </div>
                  </details>
                </section>

                <section className="detail-section">
                  <h3>人工判断</h3>
                  {item.review ? (
                    <div className={`review-result review-${item.review.decision}`}>
                      <strong>
                        {item.review.decision === "rejected" ? "Reject 已保存" : "Accept 已保存"}
                      </strong>
                      {item.review.issueCodes.length > 0 ? (
                        <p>
                          问题：{item.review.issueCodes.map((issue) => requirementReviewIssueLabels[issue]).join("、")}
                        </p>
                      ) : null}
                      <p>{item.review.notes}</p>
                      <small>记录时间：{formatDateTime(item.review.reviewedAt)}</small>
                    </div>
                  ) : (
                    <RequirementCaseReviewForm batchId={detail.summary.id} caseId={item.id} />
                  )}
                </section>
              </section>
            );
          })}
        </article>

        <aside className="detail-card">
          <h2>批次证据</h2>
          <div className="meta-list">
            <div><span className="meta-label">状态</span><strong>{evidenceLabel}</strong></div>
            <div><span className="meta-label">Reviewer</span><strong>{detail.summary.reviewer}</strong></div>
            <div><span className="meta-label">Provider / Model</span><strong>{detail.summary.provider} / {detail.summary.model}</strong></div>
            <div><span className="meta-label">Extractor / Prompt</span><strong>{detail.summary.extractorVersion} / {detail.summary.promptVersion}</strong></div>
            <div><span className="meta-label">创建时间</span><strong>{formatDateTime(detail.summary.createdAt)}</strong></div>
          </div>

          <section className="detail-section">
            <h3>批次最终质量结论</h3>
            <p className="notice">{matchGateLabel}</p>
            {detail.finalDecision ? (
              <div
                className={`review-result ${detail.finalDecision.decision === "accept_for_match" ? "review-accepted" : "review-rejected"}`}
              >
                <strong>
                  {requirementReviewFinalDecisionLabel(detail.finalDecision.decision)}
                </strong>
                <p>{detail.finalDecision.notes}</p>
                <div className="meta-list compact-meta">
                  <div>
                    <span className="meta-label">Decision Reviewer</span>
                    <strong>{detail.finalDecision.reviewer}</strong>
                  </div>
                  <div>
                    <span className="meta-label">Decision Time</span>
                    <strong>{formatDateTime(detail.finalDecision.decidedAt)}</strong>
                  </div>
                  <div>
                    <span className="meta-label">Frozen Counts</span>
                    <strong>
                      {detail.finalDecision.acceptedCount} accepted / {detail.finalDecision.rejectedCount} rejected
                    </strong>
                  </div>
                  <div>
                    <span className="meta-label">Evidence Fingerprint</span>
                    <strong className="code">{detail.finalDecision.evidenceFingerprint}</strong>
                  </div>
                </div>
                {detail.finalDecision.decision === "accept_for_match" && !detail.summary.matchReleaseEligible ? (
                  <p className="inline-error">
                    该历史结论仍被保留，但当前 Batch 已不满足正式证据条件，Match 门禁已自动撤销。
                  </p>
                ) : null}
              </div>
            ) : detail.summary.formalEvidenceEligible ? (
              <RequirementReviewFinalDecisionForm
                batchId={detail.summary.id}
                reviewer={detail.summary.reviewer}
              />
            ) : (
              <p className="notice">
                只有正好 20 条、全部完成、当前版本且非 Fixture 的证据，才能提交批次级最终结论。
              </p>
            )}
          </section>

          <section className="detail-section">
            <h3>问题分布</h3>
            {Object.keys(detail.issueCodeCounts).length === 0 ? (
              <p className="notice">尚无 rejected Case 或结构化问题。</p>
            ) : (
              <div className="meta-list">
                {Object.entries(detail.issueCodeCounts).map(([issue, count]) => (
                  <div key={issue}>
                    <span className="meta-label">
                      {requirementReviewIssueLabels[issue as keyof typeof requirementReviewIssueLabels] ?? issue}
                    </span>
                    <strong>{count}</strong>
                  </div>
                ))}
              </div>
            )}
          </section>

          <section className="detail-section">
            <h3>正式证据条件</h3>
            <p className="notice">
              需要正好 20 条、全部人工审查、没有 stale Case、Provider 不是 Fixture。满足这些条件只表示证据结构有效；只有不可变 Final Decision 为 accept_for_match 且证据仍为当前版本时，Match 门禁才会放行。
            </p>
          </section>
        </aside>
      </section>
    </>
  );
}

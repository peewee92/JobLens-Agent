import {EvaluationReviewResult} from "@/components/evaluation-review-result";
import {MaintenanceHeading} from "@/components/maintenance-heading";
import {userFacingReadError} from "@/lib/user-facing-errors";
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
    const failure = caught instanceof BackendApiError ? caught : null;
    return <ServiceError message={userFacingReadError(failure?.status, failure?.code, "暂时无法读取这份评测。已保存的结果不受影响，可以重试。")} />;
  }

  const cases = sortRequirementEvalCases(detail.cases);
  const failedCount = cases.filter((item) => !item.passed).length;

  return (
    <>
      <MaintenanceHeading title="岗位要求评测详情" returnTo="jobs"
        description="先看未通过的案例，再核对出错的原因。系统通过自动检查，不代表维护者已审核通过。">
        <Link className="button-ghost" href="/evals/requirements">返回评测记录</Link>
      </MaintenanceHeading>

      <div className="summary-grid">
        <div className="summary-card"><span>评测方式</span><strong>{detail.summary.mode === "live" ? "在线模型评测" : "离线测试"}</strong></div>
        <div className="summary-card"><span>自动检查</span><strong>{detail.summary.gatePassed ? "通过" : "失败"}</strong></div>
        <div className="summary-card"><span>通过案例</span><strong>{detail.summary.passedCases}/{detail.summary.totalCases}</strong></div>
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
              </div>
              {item.error ? <p className="inline-error">{item.error}</p> : null}
              <div className="case-grid">
                <div><span className="meta-label">缺失要求</span><strong>{item.missingRequirements.join("、") || "无"}</strong></div>
                <div><span className="meta-label">要求等级错误</span><strong>{item.wrongImportance.join("、") || "无"}</strong></div>
                <div><span className="meta-label">原文没有的能力</span><strong>{item.observedForbiddenCapabilities.join("、") || "无"}</strong></div>
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
              {item.traceRunId && <details className="jl-quality-facts"><summary>查看运行记录编号</summary><p className="code">{item.traceRunId}</p></details>}
            </section>
          ))}
        </article>

        <aside className="detail-card">
          <h2>评测指标与人工审核</h2>
          <details className="jl-quality-facts">
            <summary>查看模型、版本与记录编号</summary>
            <p className="code">{detail.summary.id}</p>
            <div className="meta-list">
              <div><span className="meta-label">服务商 / 模型</span><strong>{detail.summary.provider} / {detail.summary.model}</strong></div>
              <div><span className="meta-label">解析版本 / 提示词版本</span><strong>{detail.summary.extractorVersion} / {detail.summary.promptVersion}</strong></div>
              <div><span className="meta-label">检查规则版本</span><strong>{detail.summary.gateVersion}</strong></div>
              <div><span className="meta-label">评测时间</span><strong>{formatDateTime(detail.summary.createdAt)}</strong></div>
            </div>
          </details>

          <section className="detail-section">
            <h3>质量指标</h3>
            <div className="meta-list">
              <div><span className="meta-label">案例通过率</span><strong>{formatRate(detail.summary.casePassRate)}</strong></div>
              <div><span className="meta-label">流程成功率</span><strong>{formatRate(detail.summary.workflowSuccessRate)}</strong></div>
              <div><span className="meta-label">能力识别覆盖率</span><strong>{formatRate(detail.summary.capabilityRecall)}</strong></div>
              <div><span className="meta-label">要求等级准确率</span><strong>{formatRate(detail.summary.importanceAccuracy)}</strong></div>
              <div><span className="meta-label">原文没有的能力占比</span><strong>{formatRate(detail.summary.forbiddenCapabilityRate)}</strong></div>
            </div>
          </section>

          {detail.comparison ? (
            <section className="detail-section">
              <h3>与参考评测的差异</h3>
              <p className="code">{detail.comparison.baselineRunId}</p>
              <div className="meta-list">
                <div><span className="meta-label">案例通过率</span><strong>{formatDelta(detail.comparison.casePassRateDelta)}</strong></div>
                <div><span className="meta-label">能力识别覆盖率</span><strong>{formatDelta(detail.comparison.capabilityRecallDelta)}</strong></div>
                <div><span className="meta-label">要求等级准确率</span><strong>{formatDelta(detail.comparison.importanceAccuracyDelta)}</strong></div>
                <div><span className="meta-label">原文没有的能力占比</span><strong>{formatDelta(detail.comparison.forbiddenCapabilityRateDelta)}</strong></div>
              </div>
            </section>
          ) : null}

          <section className="detail-section">
            <h3>人工审核</h3>
            {detail.review ? (
              <EvaluationReviewResult review={detail.review} />
            ) : (
              <RequirementEvalReviewForm
                run={detail.summary}
                alreadyReviewed={false}
              />
            )}
          </section>
        </aside>
      </section>
    </>
  );
}

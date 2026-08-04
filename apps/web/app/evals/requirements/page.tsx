import Link from "next/link";

import {ServiceError} from "@/components/service-error";
import {
  BackendApiError,
  fetchAcceptedRequirementEvalBaseline,
  fetchRequirementEvalRuns,
} from "@/lib/backend";
import {formatDateTime} from "@/lib/format";
import {formatRate} from "@/lib/requirement-evals";

export const dynamic = "force-dynamic";

export default async function RequirementEvalRunsPage() {
  let page;
  let baseline;
  try {
    [page, baseline] = await Promise.all([
      fetchRequirementEvalRuns(),
      fetchAcceptedRequirementEvalBaseline(),
    ]);
  } catch (caught) {
    const message =
      caught instanceof BackendApiError
        ? caught.message
        : "读取 Requirement Eval 历史时发生未知错误。";
    return <ServiceError message={message} />;
  }

  return (
    <>
      <section className="page-heading">
        <p className="eyebrow">Requirement Eval Governance</p>
        <h1>岗位要求抽取质量审查</h1>
        <p className="lede">
          先检查缺失要求、importance 错误、禁止能力和 Trace，再决定是否把该 Live Run 设为正式 baseline。Fixture 通过不等于真实模型质量。
        </p>
        <div className="actions">
          <Link className="button" href="/evals/requirements/canary">
            打开 Canary 人工放行
          </Link>
          <Link className="button-ghost" href="/evals/requirements/manual">
            打开 20 条人工验收
          </Link>
        </div>
      </section>

      <section className="detail-card">
        <h2>当前正式 baseline</h2>
        {baseline ? (
          <div className="baseline-card">
            <div>
              <strong>{baseline.run.model}</strong>
              <p className="code">{baseline.run.id}</p>
            </div>
            <div className="meta-list compact-meta">
              <div><span className="meta-label">审查人</span><strong>{baseline.review.reviewer}</strong></div>
              <div><span className="meta-label">审查时间</span><strong>{formatDateTime(baseline.review.reviewedAt)}</strong></div>
              <div><span className="meta-label">Case 通过率</span><strong>{formatRate(baseline.run.casePassRate)}</strong></div>
            </div>
            <Link className="button-ghost" href={`/evals/requirements/${baseline.run.id}`}>
              查看 baseline 详情
            </Link>
          </div>
        ) : (
          <p className="notice">
            尚无人工接受的 live Requirement baseline。Fixture 通过不会出现在这里。
          </p>
        )}
      </section>

      <section className="detail-card">
        <div className="section-heading-row">
          <div>
            <h2>运行历史</h2>
            <p className="muted">共 {page.total} 次评测运行</p>
          </div>
        </div>
        {page.items.length === 0 ? (
          <p className="notice">尚无 Requirement Eval Run。</p>
        ) : (
          <div className="eval-run-list">
            {page.items.map((run) => (
              <article className="eval-run-card" key={run.id}>
                <div className="eval-run-card-heading">
                  <div>
                    <span className={`status-chip ${run.mode === "live" ? "status-live" : "status-fixture"}`}>
                      {run.mode}
                    </span>
                    <span className={`status-chip ${run.gatePassed ? "status-pass" : "status-fail"}`}>
                      Gate {run.gatePassed ? "通过" : "失败"}
                    </span>
                  </div>
                  <time>{formatDateTime(run.createdAt)}</time>
                </div>
                <h3>{run.model || run.provider}</h3>
                <p className="code">{run.id}</p>
                <div className="summary-grid eval-summary-grid">
                  <div className="summary-card"><span>案例通过</span><strong>{run.passedCases}/{run.totalCases}</strong></div>
                  <div className="summary-card"><span>能力召回</span><strong>{formatRate(run.capabilityRecall)}</strong></div>
                  <div className="summary-card"><span>Importance 准确率</span><strong>{formatRate(run.importanceAccuracy)}</strong></div>
                  <div className="summary-card"><span>可进入接受审核</span><strong>{run.releaseEligible ? "是" : "否"}</strong></div>
                </div>
                <div className="actions">
                  <Link className="button" href={`/evals/requirements/${run.id}`}>逐案例审查</Link>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>
    </>
  );
}

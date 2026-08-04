import Link from "next/link";

import {ServiceError} from "@/components/service-error";
import {BackendApiError, fetchRequirementAcceptanceRuns} from "@/lib/backend";
import {formatDateTime} from "@/lib/format";
import {
  requirementAcceptanceRunStatusClass,
  requirementAcceptanceRunStatusLabels,
  sortRequirementAcceptanceRuns,
} from "@/lib/requirement-acceptance-runs";

export const dynamic = "force-dynamic";

export default async function RequirementCanaryRunsPage() {
  let page;
  try {
    page = await fetchRequirementAcceptanceRuns();
  } catch (caught) {
    const message =
      caught instanceof BackendApiError
        ? caught.message
        : "读取 Requirement Canary Run 时发生未知错误。";
    return <ServiceError message={message} />;
  }

  const runs = sortRequirementAcceptanceRuns(page.items);

  return (
    <>
      <section className="page-heading">
        <p className="eyebrow">Human-Gated Requirement Canary</p>
        <h1>Requirement Canary 人工放行</h1>
        <p className="lede">
          查看真实 Provider Run 的累计调用、Case、Extraction 和 Trace 证据。只有你亲自完成检查并提交不可变的 Continue，后端才允许超过 Canary 边界继续执行。
        </p>
        <div className="actions">
          <Link className="button" href="/evals/requirements/canary/readiness">
            检查真实验收准备状态
          </Link>
          <Link className="button-ghost" href="/evals/requirements/manual">
            返回 20 条人工验收
          </Link>
          <Link className="button-ghost" href="/evals/requirements">
            返回 Requirement Eval
          </Link>
        </div>
      </section>

      <section className="detail-card">
        <div className="section-heading-row">
          <div>
            <h2>受控运行历史</h2>
            <p className="muted">
              共 {page.total} 个 Run。等待人工判断的 Run 优先显示。
            </p>
          </div>
        </div>

        {runs.length === 0 ? (
          <p className="notice">
            尚无 Acceptance Run。先使用 CLI 对正式 20-JD 数据集执行 1～3 条真实 Canary；本页面不会启动 Provider 调用。
          </p>
        ) : (
          <div className="eval-run-list">
            {runs.map((run) => (
              <article className="eval-run-card" key={run.id}>
                <div className="eval-run-card-heading">
                  <div>
                    <span
                      className={`status-chip ${requirementAcceptanceRunStatusClass(run.status)}`}
                    >
                      {requirementAcceptanceRunStatusLabels[run.status]}
                    </span>
                    {run.canaryDecision ? (
                      <span
                        className={`status-chip ${run.canaryDecision === "continue" ? "status-pass" : "status-fail"}`}
                      >
                        Canary {run.canaryDecision}
                      </span>
                    ) : null}
                  </div>
                  <time>{formatDateTime(run.updatedAt)}</time>
                </div>

                <h3>{run.title}</h3>
                <p className="code">{run.id}</p>
                <div className="summary-grid eval-summary-grid">
                  <div className="summary-card">
                    <span>累计调用</span>
                    <strong>{run.attemptedCalls}</strong>
                  </div>
                  <div className="summary-card">
                    <span>完成 Case</span>
                    <strong>{run.completedCaseCount}/20</strong>
                  </div>
                  <div className="summary-card">
                    <span>失败</span>
                    <strong>{run.failedCount}</strong>
                  </div>
                  <div className="summary-card">
                    <span>Deferred</span>
                    <strong>{run.deferredCount}</strong>
                  </div>
                </div>

                <div className="meta-list compact-meta">
                  <div>
                    <span className="meta-label">Reviewer</span>
                    <strong>{run.reviewer}</strong>
                  </div>
                  <div>
                    <span className="meta-label">Provider / Model</span>
                    <strong>{run.provider} / {run.model}</strong>
                  </div>
                  <div>
                    <span className="meta-label">Extractor / Prompt</span>
                    <strong>{run.extractorVersion} / {run.promptVersion}</strong>
                  </div>
                  <div>
                    <span className="meta-label">Batch</span>
                    <strong className="code">{run.batchId ?? "—"}</strong>
                  </div>
                </div>

                <div className="actions">
                  <Link className="button" href={`/evals/requirements/canary/${run.id}`}>
                    打开 Canary 证据工作台
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

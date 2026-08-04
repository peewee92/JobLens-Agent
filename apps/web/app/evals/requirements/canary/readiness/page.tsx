import Link from "next/link";

import {ServiceError} from "@/components/service-error";
import {
  BackendApiError,
  fetchRequirementAcceptanceReadiness,
} from "@/lib/backend";
import {
  requirementAcceptanceDatasetStateLabels,
  requirementAcceptanceNextActionClass,
  requirementAcceptanceNextActionLabels,
} from "@/lib/requirement-acceptance-runs";

export const dynamic = "force-dynamic";

type SearchParams = {
  reviewer?: string | string[];
  title?: string | string[];
  maxNewExtractions?: string | string[];
};

function first(value: string | string[] | undefined): string {
  return Array.isArray(value) ? (value[0] ?? "") : (value ?? "");
}

function budget(value: string): number {
  const parsed = Number.parseInt(value, 10);
  return Number.isInteger(parsed) && parsed >= 1 && parsed <= 20 ? parsed : 1;
}

export default async function RequirementAcceptanceReadinessPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const params = await searchParams;
  const reviewer = first(params.reviewer).trim();
  const title = first(params.title).trim();
  const maxNewExtractions = budget(first(params.maxNewExtractions));
  const backendQuery = new URLSearchParams({
    max_new_extractions: String(maxNewExtractions),
  });
  if (reviewer) backendQuery.set("reviewer", reviewer);
  if (title) backendQuery.set("title", title);

  let readiness;
  try {
    readiness = await fetchRequirementAcceptanceReadiness(backendQuery);
  } catch (caught) {
    const message =
      caught instanceof BackendApiError
        ? caught.message
        : "读取 Requirement Acceptance Readiness 时发生未知错误。";
    return <ServiceError message={message} />;
  }

  const workflowBlockers = readiness.blockers.filter(
    (item) => item.scope === "workflow",
  );
  const providerBlockers = readiness.blockers.filter(
    (item) => item.scope === "provider_execution",
  );

  return (
    <>
      <section className="page-heading">
        <p className="eyebrow">Read-only Human Gate</p>
        <h1>Requirement 真实验收准备看板</h1>
        <p className="lede">
          只读组合正式数据集、数据库版本、Provider 配置、现有 Run 与人工决策，给出唯一下一步。本页面不会迁移数据库、调用模型、创建 Run 或提交人工结论。
        </p>
        <div className="actions">
          <Link className="button-ghost" href="/evals/requirements/canary">
            返回 Canary Runs
          </Link>
          <Link className="button-ghost" href="/evals/requirements/manual">
            打开 20 条人工验收
          </Link>
        </div>
      </section>

      <section className="detail-card">
        <h2>人工参数</h2>
        <p className="muted">
          这些参数只用于定位稳定的 Run identity 和演示本次调用预算，不会从网页执行副作用。
        </p>
        <form className="filter-grid" method="get">
          <label>
            Reviewer
            <input
              defaultValue={reviewer}
              name="reviewer"
              placeholder="例如 will"
              type="text"
            />
          </label>
          <label>
            Run title
            <input
              defaultValue={title}
              name="title"
              placeholder="留空时由正式数据集生成时间推导"
              type="text"
            />
          </label>
          <label>
            本次最大新 Extraction
            <input
              defaultValue={String(maxNewExtractions)}
              max={20}
              min={1}
              name="maxNewExtractions"
              type="number"
            />
          </label>
          <div className="actions">
            <button className="button" type="submit">
              重新检查只读状态
            </button>
          </div>
        </form>
      </section>

      <section className="detail-card">
        <div className="section-heading-row">
          <div>
            <h2>唯一下一步</h2>
            <p className="muted">
              状态由 Backend Policy 动态派生，Web 不计算阈值或发布资格。
            </p>
          </div>
          <span
            className={`status-chip ${requirementAcceptanceNextActionClass(readiness.nextAction)}`}
          >
            {requirementAcceptanceNextActionLabels[readiness.nextAction]}
          </span>
        </div>

        <div className="summary-grid eval-summary-grid">
          <div className="summary-card">
            <span>正式数据集</span>
            <strong>
              {requirementAcceptanceDatasetStateLabels[readiness.datasetState]}
            </strong>
            <small>{readiness.selectedCount}/20 条</small>
          </div>
          <div className="summary-card">
            <span>数据库</span>
            <strong>
              {readiness.databaseRevision ?? "missing"}
            </strong>
            <small>Head：{readiness.migrationHead}</small>
          </div>
          <div className="summary-card">
            <span>Provider / Model</span>
            <strong>{readiness.provider || "disabled"}</strong>
            <small>{readiness.model || "未配置模型"}</small>
          </div>
          <div className="summary-card">
            <span>API Key</span>
            <strong>{readiness.apiKeyConfigured ? "已配置" : "未配置"}</strong>
            <small>仅返回存在性，不返回密钥</small>
          </div>
        </div>

        <div className="meta-list compact-meta">
          <div>
            <span className="meta-label">Workflow ready</span>
            <strong>{readiness.workflowReady ? "是" : "否"}</strong>
          </div>
          <div>
            <span className="meta-label">Provider execution allowed</span>
            <strong>{readiness.providerExecutionAllowed ? "是" : "否"}</strong>
          </div>
          <div>
            <span className="meta-label">只读证据</span>
            <strong>
              DB writes {readiness.dbWrites} / Provider calls {readiness.providerCalls}
            </strong>
          </div>
          <div>
            <span className="meta-label">累计真实调用</span>
            <strong>{readiness.attemptedCalls}</strong>
          </div>
        </div>

        {readiness.nextAction === "run_canary" ||
        readiness.nextAction === "resume_run" ? (
          <p className="notice">
            当前状态允许进入显式 CLI Operator，但网页故意不提供执行按钮。真实调用仍需要命令行双确认、成本确认和后续人工审核。
          </p>
        ) : null}

        {readiness.nextAction === "review_canary" && readiness.workbenchUrl ? (
          <div className="actions">
            <a className="button" href={readiness.workbenchUrl}>
              打开 Canary 人工证据工作台
            </a>
          </div>
        ) : null}

        {readiness.nextAction === "open_manual_review" &&
        readiness.manualReviewUrl ? (
          <div className="actions">
            <a className="button" href={readiness.manualReviewUrl}>
              打开 20 条人工验收批次
            </a>
          </div>
        ) : null}
      </section>

      <section className="detail-card">
        <h2>阻塞与人工门禁</h2>
        {readiness.blockers.length === 0 ? (
          <p className="notice">
            当前没有 Readiness blocker。仍需按照 nextAction 使用对应的 CLI Operator 或人工工作台，不能从此页面直接执行。
          </p>
        ) : (
          <div className="detail-grid">
            <article>
              <h3>Workflow blockers</h3>
              {workflowBlockers.length === 0 ? (
                <p className="muted">无。</p>
              ) : (
                <ul>
                  {workflowBlockers.map((blocker) => (
                    <li key={`${blocker.scope}-${blocker.code}`}>
                      <strong>{blocker.code}</strong>
                      <p>{blocker.message}</p>
                    </li>
                  ))}
                </ul>
              )}
            </article>
            <article>
              <h3>Provider execution blockers</h3>
              {providerBlockers.length === 0 ? (
                <p className="muted">无。</p>
              ) : (
                <ul>
                  {providerBlockers.map((blocker) => (
                    <li key={`${blocker.scope}-${blocker.code}`}>
                      <strong>{blocker.code}</strong>
                      <p>{blocker.message}</p>
                    </li>
                  ))}
                </ul>
              )}
            </article>
          </div>
        )}
      </section>

      <section className="detail-card">
        <h2>证据身份</h2>
        <div className="meta-list compact-meta">
          <div>
            <span className="meta-label">Dataset file</span>
            <strong className="code">{readiness.datasetFileName ?? "—"}</strong>
          </div>
          <div>
            <span className="meta-label">Dataset fingerprint</span>
            <strong className="code">{readiness.datasetFingerprint ?? "—"}</strong>
          </div>
          <div>
            <span className="meta-label">Run</span>
            <strong className="code">{readiness.runId ?? "—"}</strong>
          </div>
          <div>
            <span className="meta-label">Batch</span>
            <strong className="code">{readiness.batchId ?? "—"}</strong>
          </div>
          <div>
            <span className="meta-label">Reviewer</span>
            <strong>{readiness.reviewer || "未提供"}</strong>
          </div>
          <div>
            <span className="meta-label">Run title</span>
            <strong>{readiness.title || "未提供"}</strong>
          </div>
        </div>
      </section>
    </>
  );
}

import {MaintenanceHeading} from "@/components/maintenance-heading";
import Link from "next/link";
import {Pagination} from "@/components/ui/pagination";
import {parsePageOffset, readKnownPage} from "@/lib/pagination";

import {ServiceError} from "@/components/service-error";
import {BackendApiError, fetchRequirementAcceptanceRuns} from "@/lib/backend";
import {formatDateTime} from "@/lib/format";
import {
  requirementAcceptanceRunStatusClass,
  requirementAcceptanceRunStatusLabels,
  sortRequirementAcceptanceRuns,
} from "@/lib/requirement-acceptance-runs";

export const dynamic = "force-dynamic";

export default async function RequirementCanaryRunsPage({searchParams}: {searchParams: Promise<{offset?: string | string[]}>}) {
  const requestedOffset = parsePageOffset((await searchParams).offset);
  const limit = 20;
  let offset = requestedOffset;
  let adjusted = false;
  let page;
  try {
    page = await readKnownPage(requestedOffset, limit, next => fetchRequirementAcceptanceRuns(limit, next)).then(result => {
        offset = result.offset; adjusted = result.adjusted; return result.page;
      });
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
      <MaintenanceHeading title="在线模型小批验证" returnTo="jobs"
        description="先对照少量在线评测的原文和结果，再决定是否继续整批验证。查看此页不会发出模型请求。">
        <Link className="button-ghost" href="/evals/requirements/canary/readiness">检查验证准备情况</Link>
        <Link className="button-ghost" href="/evals/requirements/manual">查看 20 条人工验收</Link>
      </MaintenanceHeading>

      <section className="detail-card">
        <div className="section-heading-row">
          <div>
            <h2>验证记录</h2>
            <p className="muted">
              共 {page.total} 条记录。待人工确认的排在前面。
            </p>
          </div>
        </div>

        {runs.length === 0 ? (
          <p className="notice">
            还没有在线验证记录。维护者可以先检查准备情况，再从命令行启动少量测试。
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
                        {run.canaryDecision === "continue" ? "已确认继续" : "已确认停止"}
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
                    <span>完成案例</span>
                    <strong>{run.completedCaseCount}/20</strong>
                  </div>
                  <div className="summary-card">
                    <span>失败</span>
                    <strong>{run.failedCount}</strong>
                  </div>
                  <div className="summary-card">
                    <span>暂缓</span>
                    <strong>{run.deferredCount}</strong>
                  </div>
                </div>

                <div className="meta-list compact-meta">
                  <div>
                    <span className="meta-label">审核人</span>
                    <strong>{run.reviewer}</strong>
                  </div>
                  <div>
                    <span className="meta-label">服务商 / 模型</span>
                    <strong>{run.provider} / {run.model}</strong>
                  </div>
                  <div>
                    <span className="meta-label">解析版本 / 提示词版本</span>
                    <strong>{run.extractorVersion} / {run.promptVersion}</strong>
                  </div>
                  <div>
                    <span className="meta-label">关联批次</span>
                    <strong className="code">{run.batchId ?? "—"}</strong>
                  </div>
                </div>

                <div className="actions">
                  <Link className="button" href={`/evals/requirements/canary/${run.id}`}>
                    查看验证结果
                  </Link>
                </div>
              </article>
            ))}
          </div>
        )}
        {adjusted && <p role="status" className="jl-callout">列表已更新，已显示最后一个有效页面。</p>}
        <Pagination label="质量记录分页" offset={offset} limit={limit} count={page.items.length} total={page.total}
          href={next => next === 0 ? "/evals/requirements/canary" : `/evals/requirements/canary?offset=${next}`} />
      </section>
    </>
  );
}

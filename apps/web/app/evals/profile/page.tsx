import {MaintenanceHeading} from "@/components/maintenance-heading";
import {userFacingReadError} from "@/lib/user-facing-errors";
import Link from "next/link";
import {Pagination} from "@/components/ui/pagination";
import {parsePageOffset, readKnownPage} from "@/lib/pagination";

import {ServiceError} from "@/components/service-error";
import {
  BackendApiError,
  fetchAcceptedProfileEvalBaseline,
  fetchProfileEvalRuns,
} from "@/lib/backend";
import {formatDateTime} from "@/lib/format";
import {formatRate} from "@/lib/profile-evals";

export const dynamic = "force-dynamic";

export default async function ProfileEvalRunsPage({searchParams}: {searchParams: Promise<{offset?: string | string[]}>}) {
  const requestedOffset = parsePageOffset((await searchParams).offset);
  const limit = 20;
  let offset = requestedOffset;
  let adjusted = false;
  let page;
  let baseline;
  try {
    [page, baseline] = await Promise.all([
      readKnownPage(requestedOffset, limit, next => fetchProfileEvalRuns(limit, next)).then(result => {
        offset = result.offset; adjusted = result.adjusted; return result.page;
      }),
      fetchAcceptedProfileEvalBaseline(),
    ]);
  } catch (caught) {
    const failure = caught instanceof BackendApiError ? caught : null;
    return <ServiceError message={userFacingReadError(failure?.status, failure?.code, "暂时无法读取简历解析评测记录。已保存的评测不受影响，可以重试。")} />;
  }

  return (
    <>
      <MaintenanceHeading title="简历解析评测" returnTo="profile"
        description="检查模型是否正确读出了测试简历的技能和经历。系统先检查结果；符合条件的在线评测，才可经维护者审核选为今后的比较标准。" />

      <section className="detail-card">
        <h2>当前评测参考标准</h2>
        {baseline ? (
          <div className="baseline-card">
            <div>
              <strong>{baseline.run.model}</strong>
            </div>
            <div className="meta-list compact-meta">
              <div><span className="meta-label">审查人</span><strong>{baseline.review.reviewer}</strong></div>
              <div><span className="meta-label">审查时间</span><strong>{formatDateTime(baseline.review.reviewedAt)}</strong></div>
              <div><span className="meta-label">案例通过率</span><strong>{formatRate(baseline.run.casePassRate)}</strong></div>
            </div>
            <Link className="button-ghost" href={`/evals/profile/${baseline.run.id}`}>
              查看参考评测
            </Link>
          </div>
        ) : (
          <p className="notice">
            还没有经过人工审核并选为参考标准的在线评测。离线测试通过不会更新此标准。
          </p>
        )}
      </section>

      <section className="detail-card">
        <div className="section-heading-row">
          <div>
            <h2>评测记录</h2>
            {page.total > 0 && <p className="muted">共 {page.total} 次评测</p>}
          </div>
        </div>
        {page.items.length === 0 ? (
          <p className="notice">还没有评测记录。本页只展示结果，不会替你启动评测。</p>
        ) : (
          <div className="eval-run-list">
            {page.items.map((run) => (
              <article className="eval-run-card" key={run.id}>
                <div className="eval-run-card-heading">
                  <div>
                    <span className={`status-chip ${run.mode === "live" ? "status-live" : "status-fixture"}`}>
                      {run.mode === "live" ? "在线模型评测" : "离线测试"}
                    </span>
                    <span className={`status-chip ${run.gatePassed ? "status-pass" : "status-fail"}`}>
                      自动检查{run.gatePassed ? "已通过" : "未通过"}
                    </span>
                  </div>
                  <time>{formatDateTime(run.createdAt)}</time>
                </div>
                <h3>{run.model || run.provider}</h3>

                <div className="summary-grid eval-summary-grid">
                  <div className="summary-card"><span>案例通过</span><strong>{run.passedCases}/{run.totalCases}</strong></div>
                  <div className="summary-card"><span>技能识别覆盖率</span><strong>{formatRate(run.skillRecall)}</strong></div>
                  <div className="summary-card"><span>不应出现的事实占比</span><strong>{formatRate(run.forbiddenFactRate)}</strong></div>
                  <div className="summary-card"><span>符合审核通过条件</span><strong>{run.releaseEligible ? "是" : "否"}</strong></div>
                </div>
                <div className="actions">
                  <Link className="button" href={`/evals/profile/${run.id}`}>查看评测结果</Link>
                </div>
              </article>
            ))}
          </div>
        )}
        {adjusted && <p role="status" className="jl-callout">列表已更新，已显示最后一个有效页面。</p>}
        <Pagination label="质量记录分页" offset={offset} limit={limit} count={page.items.length} total={page.total}
          href={next => next === 0 ? "/evals/profile" : `/evals/profile?offset=${next}`} />
      </section>
    </>
  );
}

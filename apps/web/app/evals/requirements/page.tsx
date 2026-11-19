import {MaintenanceHeading} from "@/components/maintenance-heading";
import {userFacingReadError} from "@/lib/user-facing-errors";
import Link from "next/link";
import {Pagination} from "@/components/ui/pagination";
import {parsePageOffset, readKnownPage} from "@/lib/pagination";

import {ServiceError} from "@/components/service-error";
import {
  BackendApiError,
  fetchAcceptedRequirementEvalBaseline,
  fetchMvpQualityStatus,
  fetchRequirementEvalRuns,
} from "@/lib/backend";
import {formatDateTime} from "@/lib/format";
import {formatRate} from "@/lib/requirement-evals";

export const dynamic = "force-dynamic";

export default async function RequirementEvalRunsPage({searchParams}: {searchParams: Promise<{offset?: string | string[]}>}) {
  const requestedOffset = parsePageOffset((await searchParams).offset);
  const limit = 20;
  let offset = requestedOffset;
  let adjusted = false;
  let page;
  let baseline;
  let mvpQuality;
  try {
    [page, baseline, mvpQuality] = await Promise.all([
      readKnownPage(requestedOffset, limit, next => fetchRequirementEvalRuns(limit, next)).then(result => {
        offset = result.offset; adjusted = result.adjusted; return result.page;
      }),
      fetchAcceptedRequirementEvalBaseline(),
      fetchMvpQualityStatus(),
    ]);
  } catch (caught) {
    const failure = caught instanceof BackendApiError ? caught : null;
    return <ServiceError message={userFacingReadError(failure?.status, failure?.code, "暂时无法读取岗位要求评测记录。已保存的评测不受影响，可以重试。")} />;
  }

  return (
    <>
      <MaintenanceHeading title="岗位要求评测" returnTo="jobs"
        description="检查模型有没有漏读要求、把加分项误当门槛，或写出原文没有的内容。通过自动检查不等于已获人工认可。">
        <Link className="button-ghost" href="/evals/requirements/canary">查看在线小批验证</Link>
        <Link className="button-ghost" href="/evals/requirements/manual">查看 20 条人工验收</Link>
      </MaintenanceHeading>

      <section className="detail-card">
        <div className="section-heading-row">
          <div>
            <h2>离线检查结果</h2>
            <p className="muted">检查岗位要求读取和前 5 个推荐岗位的依据。模型连接测试用于排查问题，不参与这项检查。</p>
          </div>
          <span className={`status-chip ${mvpQuality.gatePassed ? "status-pass" : "status-fail"}`}>
            {mvpQuality.gatePassed ? "离线检查已通过" : "离线检查未通过"}
          </span>
        </div>
        <div className="summary-grid eval-summary-grid">
          <div className="summary-card">
            <span>岗位要求离线回放</span>
            <strong>{mvpQuality.replayPassedCases}/{mvpQuality.replayTotalCases}</strong>
            <small>{mvpQuality.replayPassed ? "通过" : "失败"}</small>
          </div>
          <div className="summary-card">
            <span>前 5 个推荐岗位</span>
            <strong>{mvpQuality.matchDemoTopJobs}/5</strong>
            <small>{mvpQuality.matchDemoEvidenceComplete ? "证据完整" : "证据不完整"}</small>
          </div>
          <div className="summary-card">
            <span>最近模型连接测试</span>
            <strong>
              {mvpQuality.providerSmokeState === "never_run"
                ? "未运行"
                : mvpQuality.providerSmokeState === "healthy"
                  ? "健康"
                  : "异常"}
            </strong>
            <small>
              {mvpQuality.providerSmokeCheckedAt
                ? `${formatDateTime(mvpQuality.providerSmokeCheckedAt)} · 普通响应 ${mvpQuality.providerSmokePlainStatusCode ?? "—"} / 结构化响应 ${mvpQuality.providerSmokeStructuredStatusCode ?? "—"}`
                : "还没有连接测试记录"}
            </small>
            <small>{mvpQuality.providerSmokeBlocking ? "会影响通过" : "不影响离线检查"}</small>
          </div>
        </div>
      </section>

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
            <Link className="button-ghost" href={`/evals/requirements/${baseline.run.id}`}>
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
          <p className="notice">还没有岗位要求评测记录。本页只展示结果，不会启动评测。</p>
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
                  <div className="summary-card"><span>能力识别覆盖率</span><strong>{formatRate(run.capabilityRecall)}</strong></div>
                  <div className="summary-card"><span>要求等级准确率</span><strong>{formatRate(run.importanceAccuracy)}</strong></div>
                  <div className="summary-card"><span>符合审核通过条件</span><strong>{run.releaseEligible ? "是" : "否"}</strong></div>
                </div>
                <div className="actions">
                  <Link className="button" href={`/evals/requirements/${run.id}`}>查看评测结果</Link>
                </div>
              </article>
            ))}
          </div>
        )}
        {adjusted && <p role="status" className="jl-callout">列表已更新，已显示最后一个有效页面。</p>}
        <Pagination label="质量记录分页" offset={offset} limit={limit} count={page.items.length} total={page.total}
          href={next => next === 0 ? "/evals/requirements" : `/evals/requirements?offset=${next}`} />
      </section>
    </>
  );
}

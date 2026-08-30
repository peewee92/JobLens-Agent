import Link from "next/link";
import {notFound} from "next/navigation";

import {ImportBatchMatch} from "@/components/import-batch-match";
import {ImportOutcomePill} from "@/components/status-pill";
import {ServiceError} from "@/components/service-error";
import {
  BackendApiError,
  fetchImportDetail,
  fetchJobDetail,
  fetchJobRequirementReleaseReadiness,
  fetchMatchRanking,
  fetchMatchReviewReadiness,
} from "@/lib/backend";
import {formatDateTime} from "@/lib/format";
import {userFacingErrorCode} from "@/lib/user-facing-errors";

export const dynamic = "force-dynamic";

export default async function ImportDetailPage({
  params,
}: {
  params: Promise<{id: string}>;
}) {
  const {id} = await params;
  let detail;
  try {
    detail = await fetchImportDetail(id);
  } catch (caught) {
    if (caught instanceof BackendApiError && caught.status === 404) {
      notFound();
    }
    const message =
      caught instanceof BackendApiError
        ? userFacingErrorCode(caught.code, "暂时无法读取这批岗位的处理结果，请稍后重试。")
        : "暂时无法读取这批岗位的处理结果，请稍后重试。";
    return <ServiceError message={message} />;
  }

  const importedJobIds = detail.items.flatMap((item) => (item.jobId ? [item.jobId] : []));
  const [rankingResult, matchReviewReadinessResult, jobDetailResults, readinessResults] = await Promise.all([
    importedJobIds.length > 0
      ? fetchMatchRanking(importedJobIds, {includeBlocked: true})
          .then((value) => ({status: "fulfilled" as const, value}))
          .catch((reason) => ({status: "rejected" as const, reason}))
      : Promise.resolve({
          status: "fulfilled" as const,
          value: {items: [], count: 0, dbWrites: 0, providerCalls: 0, traceRunsCreated: 0},
        }),
    fetchMatchReviewReadiness()
      .then((value) => ({status: "fulfilled" as const, value}))
      .catch((reason) => ({status: "rejected" as const, reason})),
    Promise.allSettled(importedJobIds.map((jobId) => fetchJobDetail(jobId))),
    Promise.allSettled(importedJobIds.map((jobId) => fetchJobRequirementReleaseReadiness(jobId))),
  ]);
  const rankingAvailable = rankingResult.status === "fulfilled";
  const rankedJobIds = new Set(
    rankingAvailable ? rankingResult.value.items.map((item) => item.jobId) : [],
  );
  const matchInputReadinessAvailable = matchReviewReadinessResult.status === "fulfilled";
  const matchInputReadyJobIds = new Set(
    matchInputReadinessAvailable ? matchReviewReadinessResult.value.reviewableJobIds : [],
  );
  const jobDetailById = new Map(
    jobDetailResults.flatMap((result) =>
      result.status === "fulfilled" ? [[result.value.id, result.value] as const] : [],
    ),
  );
  const readinessByJobId = new Map(
    readinessResults.flatMap((result) =>
      result.status === "fulfilled" ? [[result.value.jobId, result.value] as const] : [],
    ),
  );
  const matchedCount = importedJobIds.filter((jobId) => rankedJobIds.has(jobId)).length;
  const matchReadyCount = importedJobIds.filter(
    (jobId) => rankingAvailable && !rankedJobIds.has(jobId) && matchInputReadyJobIds.has(jobId),
  ).length;
  const requirementBlockedCount = importedJobIds.filter((jobId) => {
    const readiness = readinessByJobId.get(jobId);
    return !rankedJobIds.has(jobId) && !matchInputReadyJobIds.has(jobId) && readiness?.releaseEligible === false;
  }).length;
  const unknownReadinessCount = importedJobIds.length - matchedCount - matchReadyCount - requirementBlockedCount;
  const matchReadyJobs = importedJobIds.filter(
    (jobId) => rankingAvailable && !rankedJobIds.has(jobId) && matchInputReadyJobIds.has(jobId),
  );
  const requirementBlockedJobs = importedJobIds.filter((jobId) => {
    const readiness = readinessByJobId.get(jobId);
    return !rankedJobIds.has(jobId) && !matchInputReadyJobIds.has(jobId) && readiness?.releaseEligible === false;
  });
  const unknownReadinessJobs = importedJobIds.filter((jobId) => {
    if (rankedJobIds.has(jobId)) {
      return false;
    }
    const readiness = readinessByJobId.get(jobId);
    return !readiness || (
      readiness.releaseEligible && (!rankingAvailable || !matchInputReadinessAvailable)
    );
  });
  const jobLabel = (jobId: string) => {
    const job = jobDetailById.get(jobId);
    return job ? `${job.title} · ${job.company}` : `岗位 ${jobId}`;
  };

  return (
    <>
      <section className="page-heading">
        <p className="eyebrow">添加结果</p>
        <h1>这批岗位处理得怎么样</h1>
        <p className="lede">
          这里告诉你哪些岗位已经添加、哪些更新了已有信息，以及哪些没有成功处理。
        </p>
      </section>

      <div className="summary-grid">
        <div className="summary-card"><span>文件中的岗位</span><strong>{detail.received}</strong></div>
        <div className="summary-card"><span>新增</span><strong>{detail.created}</strong></div>
        <div className="summary-card"><span>信息已更新</span><strong>{detail.updated}</strong></div>
        <div className="summary-card"><span>未添加</span><strong>{detail.skipped}</strong></div>
      </div>

      {importedJobIds.length > 0 ? (
        <section className="detail-card" style={{marginBottom: "1rem"}}>
          <h2>这批岗位下一步怎么处理</h2>
          <p className="notice">
            这里只读取现有 Requirement / Match 事实，不会自动分析岗位、调用 Provider 或替你发起匹配。
          </p>
          <div className="summary-grid">
            <div className="summary-card"><span>已有当前匹配结果</span><strong>{matchedCount}</strong></div>
            <div className="summary-card"><span>要求已准备，可进入匹配</span><strong>{matchReadyCount}</strong></div>
            <div className="summary-card"><span>岗位要求还未准备好</span><strong>{requirementBlockedCount}</strong></div>
            {unknownReadinessCount > 0 ? (
              <div className="summary-card"><span>暂时无法确认</span><strong>{unknownReadinessCount}</strong></div>
            ) : null}
          </div>
          {requirementBlockedJobs.length > 0 ? (
            <section className="detail-section">
              <h3>还需处理岗位要求</h3>
              <p className="muted">先看具体阻塞原因，再决定是否进入该岗位处理；这里不会自动发起分析。</p>
              <ul>
                {requirementBlockedJobs.map((jobId) => {
                  const readiness = readinessByJobId.get(jobId);
                  return (
                    <li key={jobId} style={{marginBottom: "0.85rem"}}>
                      <Link href={`/jobs/${jobId}`}><strong>{jobLabel(jobId)}</strong></Link>
                      {readiness && readiness.blockers.length > 0 ? (
                        <ul>
                          {readiness.blockers.slice(0, 2).map((blocker) => (
                            <li key={`${jobId}-${blocker.code}`}>{blocker.message}</li>
                          ))}
                        </ul>
                      ) : (
                        <p className="muted">当前没有可展示的具体阻塞原因，请进入岗位查看最新状态。</p>
                      )}
                    </li>
                  );
                })}
              </ul>
            </section>
          ) : null}

          {matchReadyJobs.length > 0 ? (
            <section className="detail-section">
              <h3>Requirement 已准备、等待匹配</h3>
              <ul>
                {matchReadyJobs.map((jobId) => (
                  <li key={jobId}><Link href={`/jobs/${jobId}`}>{jobLabel(jobId)}</Link></li>
                ))}
              </ul>
              <ImportBatchMatch jobIds={matchReadyJobs} />
            </section>
          ) : null}

          {unknownReadinessJobs.length > 0 ? (
            <section className="detail-section">
              <h3>暂时无法确认的岗位</h3>
              <p className="muted">这些岗位的 Requirement 状态读取失败，因此不会被误报为“尚未准备”。</p>
              <ul>
                {unknownReadinessJobs.map((jobId) => (
                  <li key={jobId}><Link href={`/jobs/${jobId}`}>{jobLabel(jobId)}</Link></li>
                ))}
              </ul>
            </section>
          ) : null}

          <div className="actions">
            {matchedCount > 0 || matchReadyCount > 0 ? (
              <Link className="button" href="/recommendations">查看优先投递与继续匹配</Link>
            ) : null}
            {requirementBlockedCount > 0 ? (
              <Link className="button-ghost" href="/jobs">查看全部岗位</Link>
            ) : null}
          </div>
          <p className="muted">
            “要求已准备，可进入匹配”表示这批岗位已经通过当前 Match Input Readiness，不代表已经生成 MatchReport；真正的匹配仍必须由你显式点击发起。
          </p>
        </section>
      ) : null}

      <section className="detail-grid">
        <article className="detail-card">
          <h2>逐条处理结果</h2>
          {detail.items.length === 0 ? (
            <p className="notice">本批次没有最终 Job 输入项，可能只包含候选诊断数据。</p>
          ) : (
            <div style={{overflowX: "auto"}}>
              <table className="audit-table">
                <thead>
                  <tr>
                    <th>序号</th>
                    <th>结果</th>
                    <th>岗位</th>
                    <th>错误</th>
                  </tr>
                </thead>
                <tbody>
                  {detail.items.map((item) => (
                    <tr key={item.inputIndex}>
                      <td>{item.inputIndex}</td>
                      <td><ImportOutcomePill outcome={item.outcome} /></td>
                      <td>
                        {item.jobId ? (
                          <Link href={`/jobs/${item.jobId}`}>查看岗位</Link>
                        ) : "—"}
                      </td>
                      <td>{item.errorMessage || item.errorCode || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {detail.errors.length > 0 ? (
            <section className="detail-section">
              <h2>没有成功添加的原因</h2>
              {detail.errors.map((error) => (
                <div className="inline-error" key={`${error.index}-${error.code}`}>
                  <strong>第 {error.index} 条 · {error.code}</strong>
                  <p>{error.message}</p>
                </div>
              ))}
            </section>
          ) : null}
        </article>

        <aside className="detail-card">
          <h2>这批数据</h2>
          <div className="meta-list">
            <div><span className="meta-label">插件版本</span><strong>{detail.collectorVersion || detail.sourceVersion}</strong></div>
            <div><span className="meta-label">采集时间</span><strong>{formatDateTime(detail.collectedAt)}</strong></div>
            <div><span className="meta-label">添加时间</span><strong>{formatDateTime(detail.createdAt)}</strong></div>
          </div>

          <details className="technical-details">
            <summary>查看技术详情</summary>
            <p className="code">Import ID：{detail.importId}</p>
            <h3>候选数据统计</h3>
            <pre className="code notice">{JSON.stringify(detail.candidateSummary, null, 2)}</pre>
            <h3>采集时的筛选信息</h3>
            <pre className="code notice">{JSON.stringify(detail.searchIntentSnapshot, null, 2)}</pre>
          </details>

          <div className="actions">
            <Link className="button" href="/jobs">查看我的岗位</Link>
            <Link className="button-ghost" href="/import">继续添加岗位</Link>
          </div>
        </aside>
      </section>
    </>
  );
}

import Link from "next/link";
import {notFound} from "next/navigation";

import {ImportOutcomePill} from "@/components/status-pill";
import {ServiceError} from "@/components/service-error";
import {BackendApiError, fetchImportDetail} from "@/lib/backend";
import {formatDateTime} from "@/lib/format";

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
      caught instanceof BackendApiError ? caught.message : "读取导入审计时发生未知错误。";
    return <ServiceError message={message} />;
  }

  return (
    <>
      <section className="page-heading">
        <p className="eyebrow">Import Audit</p>
        <h1>导入批次审计</h1>
        <p className="lede">
          这里展示公开、脱敏后的批次事实。原始 candidate 和错误 raw 保留在 Backend，不通过普通 Web 页面暴露。
        </p>
        <p className="code">{detail.importId}</p>
      </section>

      <div className="summary-grid">
        <div className="summary-card"><span>收到</span><strong>{detail.received}</strong></div>
        <div className="summary-card"><span>新建</span><strong>{detail.created}</strong></div>
        <div className="summary-card"><span>更新</span><strong>{detail.updated}</strong></div>
        <div className="summary-card"><span>跳过</span><strong>{detail.skipped}</strong></div>
      </div>

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
                    <th>Index</th>
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
                          <Link className="code" href={`/jobs/${item.jobId}`}>{item.jobId}</Link>
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
              <h2>公开错误信息</h2>
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
          <h2>批次上下文</h2>
          <div className="meta-list">
            <div><span className="meta-label">Collector 版本</span><strong>{detail.collectorVersion || detail.sourceVersion}</strong></div>
            <div><span className="meta-label">采集时间</span><strong>{formatDateTime(detail.collectedAt)}</strong></div>
            <div><span className="meta-label">导入时间</span><strong>{formatDateTime(detail.createdAt)}</strong></div>
          </div>

          <section className="detail-section">
            <h3>Candidate 汇总</h3>
            <div className="summary-grid">
              <div className="summary-card"><span>总数</span><strong>{detail.candidateSummary.total}</strong></div>
              <div className="summary-card"><span>保留</span><strong>{detail.candidateSummary.kept}</strong></div>
              <div className="summary-card"><span>淘汰</span><strong>{detail.candidateSummary.rejected}</strong></div>
              <div className="summary-card"><span>未知</span><strong>{detail.candidateSummary.unknown}</strong></div>
            </div>
          </section>

          <section className="detail-section">
            <h3>搜索意图快照</h3>
            <pre className="code notice">{JSON.stringify(detail.searchIntentSnapshot, null, 2)}</pre>
          </section>

          <div className="actions">
            <Link className="button" href="/jobs">查看岗位池</Link>
            <Link className="button-ghost" href="/import">继续导入</Link>
          </div>
        </aside>
      </section>
    </>
  );
}

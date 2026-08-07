import Link from "next/link";
import {notFound} from "next/navigation";

import {ImportOutcomePill} from "@/components/status-pill";
import {ServiceError} from "@/components/service-error";
import {BackendApiError, fetchImportDetail} from "@/lib/backend";
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

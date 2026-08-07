import Link from "next/link";

import {RemoteStatusPill} from "@/components/status-pill";
import {ServiceError} from "@/components/service-error";
import {BackendApiError, fetchJobPage} from "@/lib/backend";
import type {SearchParams} from "@/lib/contracts";
import {formatDateTime, formatSalary} from "@/lib/format";
import {buildJobQuery, jobsHref, parseJobFilters} from "@/lib/query";
import {userFacingErrorCode} from "@/lib/user-facing-errors";

export const dynamic = "force-dynamic";

export default async function JobsPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const filters = parseJobFilters(await searchParams);
  let page;
  try {
    page = await fetchJobPage(buildJobQuery(filters));
  } catch (caught) {
    const message =
      caught instanceof BackendApiError
        ? userFacingErrorCode(caught.code, "暂时无法读取岗位列表，请稍后重试。")
        : "暂时无法读取岗位列表，请稍后重试。";
    return (
      <>
        <section className="page-heading">
          <p className="eyebrow">我的岗位</p>
          <h1>我的岗位</h1>
        </section>
        <ServiceError message={message} />
      </>
    );
  }

  const hasPrevious = page.offset > 0;
  const hasNext = page.offset + page.items.length < page.total;

  return (
    <>
      <section className="page-heading">
        <p className="eyebrow">我的岗位</p>
        <h1>集中查看你感兴趣的岗位</h1>
        <p className="lede">
          按关键词、城市、薪资和远程方式筛选，点进岗位后可以查看完整 JD 和岗位要求分析。
        </p>
      </section>

      <form className="panel filter-form" action="/jobs" method="get">
        <div className="field">
          <label htmlFor="q">关键词</label>
          <input id="q" name="q" defaultValue={filters.q} placeholder="Agent、RAG、公司名…" />
        </div>
        <div className="field">
          <label htmlFor="city">城市</label>
          <input id="city" name="city" defaultValue={filters.city} placeholder="武汉" />
        </div>
        <div className="field">
          <label htmlFor="minSalaryK">最低可接受 K/月</label>
          <input
            id="minSalaryK"
            name="minSalaryK"
            type="number"
            min="0"
            step="1"
            defaultValue={filters.minSalaryK}
            placeholder="20"
          />
        </div>
        <div className="field">
          <label htmlFor="remoteStatus">远程状态</label>
          <select id="remoteStatus" name="remoteStatus" defaultValue={filters.remoteStatus}>
            <option value="">全部</option>
            <option value="confirmed">支持远程</option>
            <option value="rejected">不支持远程</option>
            <option value="unknown">未说明是否远程</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="source">来源</label>
          <input id="source" name="source" defaultValue={filters.source} placeholder="boss" />
        </div>
        <div className="field">
          <label htmlFor="sort">排序</label>
          <select id="sort" name="sort" defaultValue={filters.sort}>
            <option value="latest">最近采集</option>
            <option value="salaryDesc">薪资从高到低</option>
            <option value="salaryAsc">薪资从低到高</option>
          </select>
        </div>
        <input type="hidden" name="limit" value={filters.limit} />
        <div className="filter-actions">
          <button className="button" type="submit">应用筛选</button>
          <Link className="button-ghost" href="/jobs">清空条件</Link>
          <Link className="button-secondary" href="/import">添加更多岗位</Link>
        </div>
      </form>

      <div className="result-bar">
        <span>共 {page.total} 个岗位，本页 {page.items.length} 个</span>
        <span>第 {Math.floor(page.offset / page.limit) + 1} 页</span>
      </div>

      {page.items.length === 0 ? (
        <section className="empty-state">
          <h2>没有符合当前条件的岗位</h2>
          <p>可以尝试放宽筛选条件，或者先添加更多感兴趣的岗位。</p>
          <div className="actions">
            <Link className="button" href="/jobs">清空筛选</Link>
            <Link className="button-ghost" href="/import">添加岗位</Link>
          </div>
        </section>
      ) : (
        <section className="job-list" aria-label="岗位列表">
          {page.items.map((job) => (
            <article className="job-card" key={job.id}>
              <div className="job-card-header">
                <div>
                  <h2><Link href={`/jobs/${job.id}`}>{job.title}</Link></h2>
                  <p className="company">{job.company}</p>
                </div>
                <span className="salary">{formatSalary(job.salaryMinK, job.salaryMaxK)}</span>
              </div>
              <div className="tags">
                {job.area ? <span className="tag">{job.area}</span> : null}
                <RemoteStatusPill status={job.remoteStatus} />
                <span className="tag">来源：{job.source}</span>
                <span className="tag">采集：{formatDateTime(job.collectedAt)}</span>
              </div>
            </article>
          ))}
        </section>
      )}

      <nav className="pagination" aria-label="分页">
        {hasPrevious ? (
          <Link className="button-ghost" href={jobsHref(filters, Math.max(0, page.offset - page.limit))}>
            ← 上一页
          </Link>
        ) : <span />}
        {hasNext ? (
          <Link className="button-ghost" href={jobsHref(filters, page.offset + page.limit)}>
            下一页 →
          </Link>
        ) : null}
      </nav>
    </>
  );
}

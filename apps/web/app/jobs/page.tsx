import Link from "next/link";

import {JobFilters} from "@/components/job-filters";
import {Button} from "@/components/ui/button";
import {EmptyState, PageHeading} from "@/components/ui/patterns";
import {RemoteStatusPill} from "@/components/status-pill";
import {ServiceError} from "@/components/service-error";
import {BackendApiError, fetchJobPage} from "@/lib/backend";
import type {SearchParams} from "@/lib/contracts";
import {formatDateTime, formatSalary} from "@/lib/format";
import {activeJobFilterLabels, buildJobQuery, jobsHref, parseJobFilters} from "@/lib/query";
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

  const activeFilters = activeJobFilterLabels(filters).length > 0;
  const hasPrevious = page.offset > 0;
  const hasNext = page.offset + page.items.length < page.total;

  return (
    <>
      <PageHeading kicker="求职工作台" title="我的岗位"
        description="筛选和浏览已添加的岗位。打开岗位后，可核对招聘要求和你的匹配依据。" />
      {(page.total > 0 || activeFilters || hasPrevious) && <section className="jl-panel jl-job-toolbar" aria-label="岗位筛选与操作">
        <JobFilters filters={filters} />
        <Button asChild><Link href="/import">添加岗位</Link></Button>
      </section>}

      {page.items.length > 0 && <div className="result-bar">
        <span>共 {page.total} 个岗位，本页 {page.items.length} 个</span>
        <span>第 {Math.floor(page.offset / page.limit) + 1} 页</span>
      </div>}

      {page.items.length === 0 ? (
        activeFilters ? <EmptyState title="没有符合当前条件的岗位"
          description="可以清空或调整筛选，岗位仍保留在列表里。"
          actions={<Button variant="secondary" asChild><Link href="/jobs">查看全部岗位</Link></Button>} />
        : hasPrevious ? <EmptyState title="这页没有岗位"
          description="列表可能已更新，可以回到第一页继续查看。"
          actions={<Button asChild><Link href={jobsHref(filters, 0)}>返回第一页</Link></Button>} />
        : <EmptyState title="还没添加岗位" description="粘贴一条招聘描述就能开始。现在不必先上传简历。"
          actions={<Button asChild><Link href="/import">添加第一个岗位</Link></Button>} />
      ) : (
        <section className="job-list jl-job-list" aria-label="岗位列表">
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

      {(hasPrevious || hasNext) && <nav className="pagination" aria-label="分页">
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
      </nav>}
    </>
  );
}

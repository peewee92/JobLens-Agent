import Link from "next/link";

import {JobFilters} from "@/components/job-filters";
import {OpenCatalogJob, RestoreCatalogPosition} from "@/components/job-catalog-navigation";
import {jobCatalogRowId, withJobCatalogReturn} from "@/lib/job-catalog-return";
import {JobOriginal} from "@/components/job-original";
import {Button} from "@/components/ui/button";
import {EmptyState, PageHeading} from "@/components/ui/patterns";
import {Pagination} from "@/components/ui/pagination";
import {RemoteStatusPill} from "@/components/status-pill";
import {ServiceError} from "@/components/service-error";
import {BackendApiError, fetchJobPage} from "@/lib/backend";
import type {SearchParams} from "@/lib/contracts";
import {formatDateTime, formatSalary, jobSourceLabels} from "@/lib/format";
import {lastPageOffset} from "@/lib/pagination";
import {activeJobFilterLabels, buildJobQuery, jobsHref, parseJobFilters} from "@/lib/query";
import {userFacingReadError} from "@/lib/user-facing-errors";

export const dynamic = "force-dynamic";

export default async function JobsPage({searchParams}: {searchParams: Promise<SearchParams>}) {
  const filters = parseJobFilters(await searchParams);
  let page;
  let pageAdjusted = false;
  try {
    page = await fetchJobPage(buildJobQuery(filters));
    if (page.offset > 0 && page.items.length === 0 && page.total > 0) {
      const offset = lastPageOffset(page.total, page.limit);
      page = await fetchJobPage(buildJobQuery({...filters, offset}));
      pageAdjusted = true;
    }
  } catch (caught) {
    const failure = caught instanceof BackendApiError ? caught : null;
    return <>
      <PageHeading title="我的岗位" />
      <ServiceError message={userFacingReadError(failure?.status, failure?.code, "暂时无法读取岗位列表。你可以保留筛选条件并重试。")}
        recovery={failure && [401, 403].includes(failure.status) ? "home" : "retry"} />
    </>;
  }

  const activeFilters = activeJobFilterLabels(filters).length > 0 || filters.sort !== "latest";
  const compareHref = "/agent";
  return <>
    <PageHeading kicker="求职工作台" title="我的岗位" description="浏览收藏的岗位，核对招聘原文，再比较哪些值得准备。" />

    <RestoreCatalogPosition />
    {(page.total > 0 || activeFilters || filters.offset > 0) && <section className="jl-panel jl-job-catalog" aria-labelledby="job-list-heading">
      <div className="jl-list-heading">
        <div><h2 id="job-list-heading" tabIndex={-1}>岗位列表</h2><p>打开岗位看要求，或快速查看原文。</p></div>
        <div className="jl-inline">
          {page.total > 0 && <Button variant="secondary" asChild><Link href={compareHref}>比较岗位</Link></Button>}
          <Button asChild><Link href="/import">添加岗位</Link></Button>
        </div>
      </div>
      <JobFilters filters={filters} />
    </section>}

    {pageAdjusted && <p className="jl-callout" role="status">列表刚刚有变化，已显示最后一个有结果的页面。筛选条件没有改变。</p>}

    {page.items.length === 0 ? (
      activeFilters ? <EmptyState title="没有符合当前条件的岗位" description="可以清空或调整条件；已添加的岗位还在。"
        actions={<Button variant="secondary" asChild><Link href="/jobs">清空筛选</Link></Button>} />
      : <EmptyState title="还没添加岗位" description="粘贴一条招聘描述就能开始，现在不必先上传简历。"
        actions={<Button asChild><Link href="/import">添加第一个岗位</Link></Button>} />
    ) : (
      <section className="jl-panel jl-job-results" aria-label="岗位搜索结果">
        <ul className="jl-job-table">
          {page.items.map((job) => {
            const labels = jobSourceLabels(job.source);
            const rowId = jobCatalogRowId(job.id);
            const href = withJobCatalogReturn(`/jobs/${encodeURIComponent(job.id)}`, jobsHref(filters, page.offset));
            return <li key={job.id} className="jl-job-row">
              <div className="jl-job-name">
                <h3><OpenCatalogJob id={rowId} rowId={rowId} href={href}>{job.title}</OpenCatalogJob></h3>
                <p>{job.company}{job.area && ` · ${job.area}`}</p>
              </div>
              <div className="jl-job-meta">
                <strong>{formatSalary(job.salaryMinK, job.salaryMaxK)}</strong>
                <RemoteStatusPill status={job.remoteStatus} />
              </div>
              <p className="jl-job-source">{labels.source}<span>{labels.recordedAt}：{formatDateTime(job.collectedAt)}</span></p>
              <JobOriginal jobId={job.id} title={job.title} company={job.company} href={href} rowId={rowId} />
            </li>;
          })}
        </ul>
        <Pagination offset={page.offset} limit={page.limit} count={page.items.length} total={page.total} href={offset => jobsHref(filters, offset)} />
      </section>
    )}
  </>;
}

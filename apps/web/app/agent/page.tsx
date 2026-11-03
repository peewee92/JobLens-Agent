import {CareerAgentHitlPanel} from "@/components/career-agent-hitl-panel";
import {systemReadinessNotice} from "@/components/system-readiness-notice";
import {BackendApiError, fetchJobPage, fetchJobDetail} from "@/lib/backend";
import type {JobListItem} from "@/lib/contracts";
import {parseAgentScope} from "@/lib/agent-job-scope";

export const dynamic = "force-dynamic";

export default async function AgentPage({searchParams}: {searchParams: Promise<{jobId?: string | string[]; scopeJobId?: string | string[]}>}) {
  const query = await searchParams;
  const requested = query.jobId;
  const scope = parseAgentScope(query.scopeJobId);
  const initialJobId = typeof requested === "string" && requested.length <= 100 ? requested : undefined;
  const notice = await systemReadinessNotice("/agent");
  if (notice) return notice;
  let jobs: JobListItem[] = [];
  let pageOffset = 0;
  let hasMore = false;
  let error: string | null = query.scopeJobId !== undefined && (!scope || requested !== undefined)
    ? "岗位范围无效，请返回岗位列表重新选择；不会自动选择其他岗位。"
    : requested !== undefined && (!initialJobId || !initialJobId.trim())
    ? "指定岗位标识无效，请返回原工作区核对；不会自动选择其他岗位。" : null;
  try {
    const page = await fetchJobPage(new URLSearchParams({limit: "20", offset: "0"}));
    jobs = error ? [] : page.items;
    pageOffset = page.items.length;
    hasMore = page.items.length > 0 && pageOffset < page.total;
    const pinned = scope ?? (initialJobId ? [initialJobId] : []);
    if (!error && pinned.length) {
      const missing = pinned.filter(id => !jobs.some(job => job.id === id));
      try { jobs = [...await Promise.all(missing.map(id => fetchJobDetail(id))), ...jobs]; }
      catch { jobs = []; error = "无法读取所选岗位，请返回岗位列表核对；不会自动替换或缩小原范围。"; }
    }
  } catch (caught) {
    error = caught instanceof BackendApiError ? caught.message : "暂时无法读取岗位。";
  }

  return (
    <>
      <section className="page-heading">
        <p className="eyebrow">岗位比较与准备</p>
        <h1>比较岗位，确认目标并开始准备</h1>
        <p>先看哪些岗位值得投入，以及理由和未知条件；确认目标后保存差距、准备材料与行动。刷新后能继续查看本次分析，不会自动重算或投递。</p>
      </section>
      {error ? (
        <section className="card"><p>{error}</p></section>
      ) : jobs.length === 0 ? (
        <section className="card"><p>当前没有可分析岗位，请先添加岗位并完成 Match。</p></section>
      ) : null}
      {initialJobId && !error && <section className="card"><p>已保留原工作区的岗位范围。此处只读取已有匹配报告；资料变化后，旧报告可能不再适用，不会自动重算或调用模型。</p><a href={`/jobs/${encodeURIComponent(initialJobId)}`}>核对该岗位及已保存的匹配报告</a></section>}
      {scope && !error && <section className="card"><p>已带回原来选择的 {scope.length} 个岗位。岗位或资料可能已变化，请重新检查后再分析。</p></section>}
      <CareerAgentHitlPanel jobs={jobs} initialJobId={initialJobId} initialScope={scope ?? undefined} initialPageOffset={pageOffset} initialHasMore={hasMore} />
    </>
  );
}

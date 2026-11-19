import Link from "next/link";
import {Button} from "@/components/ui/button";
import {EmptyState, PageHeading} from "@/components/ui/patterns";
import {Callout} from "@/components/ui/primitives";
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
      <PageHeading kicker="第 3 步 · 比较并准备" title="比较岗位"
        description="先看哪些岗位值得投入、为什么、还有什么要核实；确认目标后，再准备简历与面试。" />
      {error ? (
        <Callout tone="danger" role="alert"><p>{error}</p><Link className="jl-text-link" href="/jobs">返回我的岗位</Link></Callout>
      ) : jobs.length === 0 ? (
        <EmptyState title="还没有岗位可以比较"
          description="添加岗位并核对要求后，再用已确认的经历比较。你可以先添加岗位，也可以先确认职业资料。"
          actions={<><Button asChild><Link href="/import">添加岗位</Link></Button>
            <Link className="jl-text-link" href="/profile">确认职业资料</Link></>} />
      ) : null}
      {initialJobId && !error && <Callout className="jl-comparison-scope"><p>已保留原工作区的岗位范围。这里只读取已有匹配报告，不会自动重算或调用模型。</p><Link className="jl-text-link" href={`/jobs/${encodeURIComponent(initialJobId)}`}>核对该岗位及已保存的匹配报告</Link></Callout>}
      {scope && !error && <Callout className="jl-comparison-scope">已带回原来选择的 {scope.length} 个岗位。请检查当前输入和可用报告。</Callout>}
      <CareerAgentHitlPanel jobs={jobs} initialJobId={initialJobId} initialScope={scope ?? undefined} initialPageOffset={pageOffset} initialHasMore={hasMore} />
    </>
  );
}

import {CareerAgentHitlPanel} from "@/components/career-agent-hitl-panel";
import {BackendApiError, fetchJobPage} from "@/lib/backend";
import type {JobListItem} from "@/lib/contracts";

export const dynamic = "force-dynamic";

export default async function AgentPage() {
  let jobs: JobListItem[] = [];
  let error: string | null = null;
  try {
    const page = await fetchJobPage(new URLSearchParams({limit: "20", offset: "0"}));
    jobs = page.items;
  } catch (caught) {
    error = caught instanceof BackendApiError ? caught.message : "暂时无法读取岗位。";
  }

  return (
    <>
      <section className="page-heading">
        <p className="eyebrow">Career Agent · Durable HITL</p>
        <h1>让 Agent 连续完成岗位排序和能力差距分析</h1>
        <p>这是最小可恢复流程：先排序，再由你确认目标岗位，最后继续能力差距分析。刷新页面后，等待确认的 Run 仍可恢复。</p>
      </section>
      {error ? (
        <section className="card"><p>{error}</p></section>
      ) : jobs.length === 0 ? (
        <section className="card"><p>当前没有可分析岗位，请先添加岗位并完成 Match。</p></section>
      ) : (
        <CareerAgentHitlPanel jobs={jobs} />
      )}
    </>
  );
}

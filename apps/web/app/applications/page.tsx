import Link from "next/link";
import {Button} from "@/components/ui/button";
import {EmptyState, PageHeading} from "@/components/ui/patterns";
import {Badge, Panel} from "@/components/ui/primitives";
import {BackendApiError, fetchWorkbenchWorkspacePage} from "@/lib/backend";
import {workspaceStatusLabels} from "@/lib/workbench";

export const dynamic = "force-dynamic";

export default async function ApplicationsPage({searchParams}: {searchParams: Promise<{offset?: string}>}) {
  const raw = (await searchParams).offset ?? "0";
  if (!/^\d{1,6}$/.test(raw) || Number(raw) > 100000) return <>
    <PageHeading title="工作区页码无效" />
    <Link className="jl-text-link" href="/applications">返回第一页</Link>
  </>;
  const offset = Number(raw);
  try {
    const page = await fetchWorkbenchWorkspacePage(offset);
    return <>
      <PageHeading kicker="求职工作台" title="全部求职工作区"
        description="继续准备简历、面试和行动。这里按最近更新排列，不会自动分析或投递。" />
      {page.items.length ? <Panel><ul className="jl-workspace-list">{page.items.map(workspace => <li key={workspace.workspaceId}>
        <div><Link className="jl-text-link" href={`/applications/${encodeURIComponent(workspace.workspaceId)}`}>{workspace.title}</Link>
          <p>{workspace.openActionCount} 项待完成行动</p></div>
        <Badge>{workspaceStatusLabels[workspace.status] ?? "状态待核实"}</Badge>
      </li>)}</ul></Panel> : offset > 0
        ? <EmptyState title="这一页没有工作区" description="记录可能已更新，可以返回第一页查看。"
          actions={<Button variant="secondary" asChild><Link href="/applications">返回第一页</Link></Button>} />
        : <EmptyState title="还没有准备工作区" description="先比较岗位并确认目标，就能为它建立准备工作区。"
          actions={<Button asChild><Link href="/agent">去比较岗位</Link></Button>} />}
      <nav className="jl-inline jl-comparison-scope" aria-label="工作区分页与导航">{offset > 0 && <Link href={`/applications?offset=${Math.max(0, offset - 20)}`}>上一页</Link>}
        {page.hasMore && <Link href={`/applications?offset=${offset + 20}`}>下一页</Link>}
        <Link className="jl-text-link" href="/">返回求职工作台</Link></nav>
    </>;
  } catch (error) {
    return <>
      <PageHeading title="暂时无法读取工作区" />
      <p>{error instanceof BackendApiError ? "请检查本地服务和数据库后重试，已有记录不会因此丢失。" : "请稍后重试。"}</p>
      <Link className="jl-text-link" href={`/applications?offset=${offset}`}>重试</Link>
    </>;
  }
}

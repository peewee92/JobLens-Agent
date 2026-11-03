import Link from "next/link";
import {BackendApiError, fetchWorkbenchWorkspacePage} from "@/lib/backend";
import {workspaceStatusLabels} from "@/lib/workbench";

export const dynamic = "force-dynamic";
export default async function ApplicationsPage({searchParams}: {searchParams: Promise<{offset?: string}>}) {
  const raw = (await searchParams).offset ?? "0";
  if (!/^\d{1,6}$/.test(raw) || Number(raw) > 100000) return <section className="card"><h1>工作区页码无效</h1><Link href="/applications">返回第一页</Link></section>;
  const offset = Number(raw);
  try {
    const page = await fetchWorkbenchWorkspacePage(offset);
    return <section className="card stack-md"><h1>全部求职工作区</h1>
      <p>这里只读取已保存的工作区和行动进度，不会启动分析或自动投递。工作区随最近变更排序，翻页期间变化可能调整顺序。</p>
      {page.items.length ? <ul>{page.items.map(workspace => <li key={workspace.workspaceId}>
        <Link href={`/applications/${encodeURIComponent(workspace.workspaceId)}`}>{workspace.title}</Link>
        <p>{workspaceStatusLabels[workspace.status] ?? "状态待核实"} · {workspace.openActionCount} 项待完成行动</p>
      </li>)}</ul> : <p>本页没有工作区。</p>}
      <div className="actions">{offset > 0 && <Link href={`/applications?offset=${Math.max(0, offset - 20)}`}>上一页</Link>}
        {page.hasMore && <Link href={`/applications?offset=${offset + 20}`}>下一页</Link>}
        <Link href="/">返回求职工作台</Link></div>
    </section>;
  } catch (error) {
    return <section className="card"><h1>暂时无法读取工作区</h1><p>{error instanceof BackendApiError ? "请检查本地服务和数据库后重试，已有记录不会因此丢失。" : "请稍后重试。"}</p><Link href={`/applications?offset=${offset}`}>重试</Link></section>;
  }
}

import Link from "next/link";
import {BackendApiError, backendJson} from "@/lib/backend";
import type {SavedCareerAnalysis} from "@/lib/contracts";
import {SavedCareerAnalysisView} from "@/components/saved-career-analysis-view";

export const dynamic = "force-dynamic";

export default async function AnalysisResultPage({params}: {params: Promise<{threadId: string}>}) {
  const {threadId} = await params;
  const backHref = `/agent?threadId=${encodeURIComponent(threadId)}`;
  try {
    const result = await backendJson<SavedCareerAnalysis>(`/api/v1/career-agent/runs/${encodeURIComponent(threadId)}/result`);
    return <SavedCareerAnalysisView result={result} backHref={backHref} />;
  } catch (error) {
    return <section className="card stack-md"><h1>暂时无法打开已保存结果</h1>
      <p>{error instanceof BackendApiError && error.status === 404
        ? "此运行不存在，或只保存了旧指纹，没有完整历史材料。系统不会重新计算来冒充原结果。"
        : "结果读取失败，已保存材料不会因此丢失。请确认后端与数据库迁移正常后刷新。"}</p>
      <Link href={backHref}>返回运行，查看状态或开始新分析</Link></section>;
  }
}

import Link from "next/link";
import {BackendApiError, backendJson, fetchJobDetail, fetchMatchReportHistory} from "@/lib/backend";
import type {CareerAgentRunState, SavedCareerAnalysis} from "@/lib/contracts";
import {rankingPreflight, type RankingOmission} from "@/lib/agent-ranking-preflight";
import {SavedCareerAnalysisView} from "@/components/saved-career-analysis-view";
import {savedMatchSupport} from "@/lib/saved-match-support";

export const dynamic = "force-dynamic";

export default async function AnalysisResultPage({params}: {params: Promise<{threadId: string}>}) {
  const {threadId} = await params;
  const backHref = `/agent?threadId=${encodeURIComponent(threadId)}`;
  try {
    const result = await backendJson<SavedCareerAnalysis>(`/api/v1/career-agent/runs/${encodeURIComponent(threadId)}/result`);
    const ids = [...new Set([...(result.unrankedJobIds ?? []), ...(result.unanalysedJobIds ?? [])])]
      .filter(id => /^[A-Za-z0-9_-]{1,100}$/.test(id)).slice(0, 50);
    const params = new URLSearchParams(ids.map(id => ["jobId", id]));
    const [run, labels, currentOmissions, matchSupport] = await Promise.all([
      backendJson<CareerAgentRunState>(`/api/v1/career-agent/runs/${encodeURIComponent(threadId)}`).catch(() => null),
      Promise.allSettled(ids.map(id => fetchJobDetail(id))).then(responses => Object.fromEntries(
        responses.flatMap((item, index) => item.status === "fulfilled" && item.value.id === ids[index]
          ? [[ids[index], item.value.title]] : []))),
      ids.length ? backendJson<unknown>(`/api/v1/match-ranking/preflight?${params}`)
        .then(body => rankingPreflight(ids, body).omissions).catch((): RankingOmission[] => []) : [],
      Promise.all(result.bindings.filter(binding => result.selectedJobIds.includes(binding.jobId)).slice(0, 20)
        .map(async binding => {
          try {
            return [binding.jobId, savedMatchSupport(result, binding, await fetchMatchReportHistory(binding.jobId))] as const;
          } catch {
            return [binding.jobId, {partial: [], matched: []}] as const;
          }
        })).then(entries => Object.fromEntries<ReturnType<typeof savedMatchSupport>>(entries)),
    ]);
    const savedScope = run?.threadId === threadId && run.resultId === result.resultId
      ? {requested: run.requestedJobIds, compared: run.rankedJobIds.length} : undefined;
    return <SavedCareerAnalysisView result={result} backHref={backHref}
      savedScope={savedScope} additionalLabels={labels} currentOmissions={currentOmissions}
      savedPartialSupport={Object.fromEntries(Object.entries(matchSupport).map(([id, support]) => [id, support.partial]))}
      savedMatchedSupport={Object.fromEntries(Object.entries(matchSupport).map(([id, support]) => [id, support.matched]))} />;
  } catch (error) {
    return <section className="card stack-md"><h1>暂时无法打开已保存结果</h1>
      <p>{error instanceof BackendApiError && error.status === 404
        ? "此运行不存在，或只保存了旧指纹，没有完整历史材料。系统不会重新计算来冒充原结果。"
        : "结果读取失败，已保存材料不会因此丢失。请确认后端与数据库迁移正常后刷新。"}</p>
      <Link href={backHref}>返回运行，查看状态或开始新分析</Link></section>;
  }
}

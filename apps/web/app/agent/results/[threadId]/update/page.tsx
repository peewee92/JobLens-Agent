import Link from "next/link";
import {backendJson, BackendApiError} from "@/lib/backend";
import type {AnalysisUpdatePlan} from "@/lib/contracts";
import {AnalysisUpdatePlanView} from "@/components/analysis-update-plan-view";

export const dynamic = "force-dynamic";
export default async function AnalysisUpdatePage({params, searchParams}: {
  params: Promise<{threadId: string}>; searchParams: Promise<{scope?: string}>;
}) {
  const {threadId} = await params;
  const {scope = "targets"} = await searchParams;
  const base = `/agent/results/${encodeURIComponent(threadId)}`;
  if (scope !== "targets" && scope !== "batch") return <section className="card"><h1>请选择原目标或原批次</h1><Link href={`${base}/update`}>重新选择更新范围</Link></section>;
  try {
    const plan = await backendJson<AnalysisUpdatePlan>(`/api/v1/career-agent/runs/${encodeURIComponent(threadId)}/update-plan?scope=${scope}`);
    return <AnalysisUpdatePlanView plan={plan} />;
  } catch (error) {
    return <section className="card stack-md"><h1>暂时无法完成更新预检</h1>
      <p>{error instanceof BackendApiError && error.status === 404 ? "原运行不存在或没有完整保存结果，不能据此恢复原分析范围。" : "输入读取失败，请检查后端与数据库后重试；本页没有启动模型或改写旧结果。"}</p>
      <Link href={base}>返回原分析，核对保存状态</Link>
    </section>;
  }
}

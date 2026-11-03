import Link from 'next/link';
import {backendJson, BackendApiError} from '@/lib/backend';
import type {AnalysisComparison} from '@/lib/contracts';
import {AnalysisComparisonView} from '@/components/analysis-comparison-view';
export const dynamic = 'force-dynamic';
export default async function AnalysisComparisonPage({params}: {params: Promise<{threadId: string}>}) {
  const {threadId} = await params;
  const base = `/agent/results/${encodeURIComponent(threadId)}`;
  try {
    const comparison = await backendJson<AnalysisComparison>(`/api/v1/career-agent/runs/${encodeURIComponent(threadId)}/comparison`);
    return <AnalysisComparisonView comparison={comparison} />;
  } catch (error) {
    return <section className="error-panel"><h1>暂时不能比较两份保存结果</h1>
      <p>{error instanceof BackendApiError ? error.message : '读取失败，请核对后端后刷新；本页没有执行更新，也不会用最新报告冒充历史。'}</p>
      <Link href={base}>返回本次结果，核对保存状态</Link></section>;
  }
}

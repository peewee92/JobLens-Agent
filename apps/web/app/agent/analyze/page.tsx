import Link from 'next/link';
import {backendJson, BackendApiError} from '@/lib/backend';
import type {InitialScopePlan} from '@/lib/contracts';
import {agentScopeHref, parseAgentScope, initialScopeAnalysisHref, jobDetailWithAgentScope, profileWithAgentScope} from '@/lib/agent-job-scope';
import {AnalysisPlanItems} from '@/components/analysis-update-plan-view';
import {InitialScopeStart} from '@/components/initial-scope-start';
import {systemReadinessNotice} from '@/components/system-readiness-notice';

export const dynamic = 'force-dynamic';
export default async function InitialScopePage({searchParams}: {searchParams: Promise<{scopeJobId?: string | string[]}>}) {
  const ids = parseAgentScope((await searchParams).scopeJobId);
  if (!ids) return <section className="card"><h1>请先选择明确的岗位范围</h1><Link href="/agent">返回选择岗位</Link></section>;
  const notice = await systemReadinessNotice(initialScopeAnalysisHref(ids));
  if (notice) return notice;
  try {
    const plan = await backendJson<InitialScopePlan>('/api/v1/career-agent/initial-scope-plan', {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({jobIds: ids}),
    });
    // Never accept a shortened or substituted scope as this user's original request.
    if (plan.items.length !== ids.length || plan.items.some((item, i) => item.jobId !== ids[i])) throw new Error('scope_mismatch');
    return <>
      <section className="page-heading"><p className="eyebrow">当前事实 · 分析预检</p><h1>先核对这批岗位，再启动分析</h1>
        <p>当前职业资料 {plan.profileVersion ? `v${plan.profileVersion}` : '尚未确认'}、求职意向 {plan.searchIntentVersion ? `v${plan.searchIntentVersion}` : '尚未确认'}。</p>
        <Link href={agentScopeHref(ids)}>返回原岗位范围</Link>
        <a href={initialScopeAnalysisHref(ids)}>重新预检原范围</a>
      </section>
      <section className="card stack-md"><h2>这次处理范围</h2>
        <p>{plan.items.length} 个岗位：{plan.reusableJobIds.length} 个可复用，{plan.nextJobIds.length} 个进入首批重算候选；每次最多新增分析 {plan.maxNewAnalyses} 个岗位。</p>
        <p className="notice">当前仅预检，没有重算、保存新结果或调用模型。启动时会再次检查事实版本，旧报告保留；没有可靠建议时不会填满目标名单。</p>
        {(!plan.profileId || !plan.searchIntentId) && <Link href={profileWithAgentScope(ids[0], ids)}>先确认职业资料和求职意向</Link>}
      </section>
      <section className="card stack-md"><h2>逐项检查</h2><AnalysisPlanItems items={plan.items.map(item => ({...item,
        repairHref: item.repairHref === '/profile' ? profileWithAgentScope(item.jobId, ids) : jobDetailWithAgentScope(item.jobId, ids),
      }))} /></section>
      <InitialScopeStart plan={plan} />
    </>;
  } catch (error) {
    return <section className="card stack-md"><h1>暂时无法完成这批岗位的预检</h1>
      <p>{error instanceof BackendApiError ? error.message : '返回的岗位范围无法核对，请重试；没有启动分析或改写旧结果。'}</p>
      <Link href={agentScopeHref(ids)}>返回原岗位范围并重试</Link>
    </section>;
  }
}

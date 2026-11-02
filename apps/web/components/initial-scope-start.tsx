'use client';
import Link from 'next/link';
import {useEffect, useState} from 'react';
import type {InitialScopePlan, CareerAgentRunState} from '@/lib/contracts';
import {createInitialScopeCommand, forgetInitialScopeCommand, loadInitialScopeCommand, sendInitialScopeCommand, type InitialScopeCommand} from '@/lib/initial-scope-command';
import {runHref} from '@/lib/career-agent-commands';

export function InitialScopeStart({plan}: {plan: InitialScopePlan}) {
  const [command, setCommand] = useState<InitialScopeCommand | null>(null);
  const [ready, setReady] = useState(false), [busy, setBusy] = useState(false), [message, setMessage] = useState('');
  const ids = plan.items.map(item => item.jobId);
  const scope = JSON.stringify([...ids].sort());
  useEffect(() => {
    setReady(false); setCommand(null); setMessage('');
    try {setCommand(loadInitialScopeCommand(window.localStorage, JSON.parse(scope))); setReady(true);}
    catch {setMessage('本地请求无法读取，请先到岗位分析页核对最近运行。');}
  }, [scope]);
  async function start() {
    setBusy(true); setMessage('正在保存原请求并启动分析…');
    try {
      const original = loadInitialScopeCommand(window.localStorage, ids) ?? createInitialScopeCommand(plan, () => crypto.randomUUID());
      setCommand(original);
      const response = await sendInitialScopeCommand(window.localStorage, original);
      const body = await response.json();
      if (!response.ok) throw new Error(body.error?.message ?? '无法确认结果，请查看这次运行或重试原请求。');
      const state = body as CareerAgentRunState;
      if (state.threadId !== original.body.threadId) throw new Error('响应与原请求不一致，请核对运行。');
      window.location.assign(runHref(state.threadId));
    } catch (e) {setMessage(e instanceof Error ? e.message : '网络未返回结果，请查看运行或重试原请求。');}
    finally {setBusy(false);}
  }
  return <section className="card stack-md"><h2>明确启动这批分析</h2>
    <p>复用仍有效的报告，每次最多重算 5 个无需模型的岗位。已有报告不会被覆盖；需要模型或输入未就绪时保留具体阻断，不伪造推荐。</p>
    {!plan.items.some(item => ['reuse', 'ready', 'deferred'].includes(item.status)) && <p>当前没有可直接处理的岗位。请先按上方入口修复输入或单独授权模型；也可以保存等待状态。</p>}
    <button className="button primary" disabled={busy || !ready || (!command && (!plan.profileId || !plan.searchIntentId || !ids.length))} onClick={() => void start()}>{command ? '重试原分析请求' : '启动分析（不调用模型）'}</button>
    {command && <><Link href={runHref(command.body.threadId)}>查看这次运行</Link><p>原请求已保留。刷新不会自动执行，网络重试不创建新的分析。</p>
      <button className="button secondary" disabled={busy} onClick={() => {
        try {forgetInitialScopeCommand(window.localStorage, command); setCommand(null); setMessage('已清除本地请求，服务端历史仍保留。');}
        catch {setMessage('请求已变化，请刷新并核对运行。');}
      }}>已核对运行，清除本地请求</button></>}
    {message && <p role="status">{message}</p>}
  </section>;
}

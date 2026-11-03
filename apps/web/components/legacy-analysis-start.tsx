'use client';
import Link from 'next/link';
import {useEffect, useState} from 'react';
import type {LegacyWorkspaceAnalysisPlan, CareerAgentRunState} from '@/lib/contracts';
import {createLegacyAnalysis, forgetLegacyAnalysis, loadLegacyAnalysis, sendLegacyAnalysis, type LegacyAnalysisCommand} from '@/lib/legacy-analysis-command';
import {runHref} from '@/lib/career-agent-commands';

export function LegacyAnalysisStart({plan}: {plan: LegacyWorkspaceAnalysisPlan}) {
  const [command, setCommand] = useState<LegacyAnalysisCommand | null>(null);
  const [ready, setReady] = useState(false), [busy, setBusy] = useState(false), [message, setMessage] = useState('');
  useEffect(() => { try {setCommand(loadLegacyAnalysis(window.localStorage, plan.workspaceId)); setReady(true);} catch {setMessage('本地请求无法读取，请先核对最近运行。');} }, [plan.workspaceId]);
  async function start() {
    setBusy(true); setMessage('正在保存原请求并启动分析…');
    try {
      const original = loadLegacyAnalysis(window.localStorage, plan.workspaceId) ?? createLegacyAnalysis(plan, () => crypto.randomUUID());
      setCommand(original);
      const response = await sendLegacyAnalysis(window.localStorage, original);
      const data = await response.json();
      if (!response.ok) throw new Error(data.error?.message ?? '无法确认结果，请查看运行或重试原请求。');
      const state = data as CareerAgentRunState;
      if (state.threadId !== original.body.threadId) throw new Error('响应与请求不一致，请核对运行。');
      window.location.assign(runHref(state.threadId));
    } catch (e) {setMessage(e instanceof Error ? e.message : '网络未返回结果，请查看运行或重试原请求。');}
    finally {setBusy(false);}
  }
  return <div>
    <p>使用当前固定事实和已有规则；本次不会调用模型。需要模型或输入未就绪时会保留阻断，不伪造结论。</p>
    <button disabled={busy || !ready || (!command && (!plan.profileId || !plan.searchIntentId))} onClick={() => void start()}>{command ? '重试原分析请求' : '启动此岗位分析'}</button>
    {command && <><Link href={runHref(command.body.threadId)}>查看这次运行</Link><p>刷新不会自动发送；核对原运行后才能清除本地请求。</p>
      <button disabled={busy} onClick={() => {try {forgetLegacyAnalysis(window.localStorage, command); setCommand(null); setMessage('已清除本地请求，服务端记录保留。');} catch {setMessage('请求发生变化，请刷新后核对。');}}}>已核对运行，清除本地请求</button></>}
    {message && <p role="status">{message}</p>}
  </div>;
}

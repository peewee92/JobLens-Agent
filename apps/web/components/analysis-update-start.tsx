'use client';
import Link from 'next/link';
import {useEffect, useState} from 'react';
import type {AnalysisUpdatePlan, CareerAgentRunState} from '@/lib/contracts';
import {createUpdateCommand, forgetUpdateCommand, loadUpdateCommand, sendUpdateCommand, type UpdateCommand} from '@/lib/analysis-update-command';
import {runHref} from '@/lib/career-agent-commands';
export function AnalysisUpdateStart({plan}: {plan: AnalysisUpdatePlan}) {
  const [command, setCommand] = useState<UpdateCommand | null>(null);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [rejected, setRejected] = useState(false);
  const [storageReady, setStorageReady] = useState(false);
  const runnable = plan.items.length > 0 && !!plan.profileId && !!plan.searchIntentId;
  useEffect(() => {
    try {setCommand(loadUpdateCommand(window.localStorage, plan.sourceThreadId, plan.scope)); setStorageReady(true);}
    catch (e) {setMessage(e instanceof Error ? e.message : '无法读取原请求，请核对最近运行。');}
  }, [plan.sourceThreadId, plan.scope]);
  async function start() {
    setBusy(true); setMessage('正在保存更新请求并启动新运行…'); setRejected(false);
    try {
      const original = loadUpdateCommand(window.localStorage, plan.sourceThreadId, plan.scope) ?? createUpdateCommand(plan, () => crypto.randomUUID());
      setCommand(original);
      const response = await sendUpdateCommand(window.localStorage, original);
      if (!response.ok) {
        setRejected(response.status === 409 || response.status === 422);
        const body = await response.json();
        throw new Error(body.error?.message ?? '未能确认更新状态，请查看运行或重试原请求。');
      }
      const state = await response.json() as CareerAgentRunState;
      if (state.threadId !== original.body.threadId) throw new Error('响应与请求不一致，请核对运行状态。');
      // Keep the receipt through navigation: refresh or a lost response never creates another run.
      window.location.assign(runHref(state.threadId));
    } catch (e) {setMessage(e instanceof Error ? e.message : '网络未返回结果，请查看运行或重试原请求。');}
    finally {setBusy(false);}
  }
  return <section className="card stack-md"><h2>创建新的分析</h2>
    <p>使用兼容报告，并按当前固定事实每次最多重算 5 个可由规则完成的岗位，不调用模型。其余进度保存在运行中，需你明确继续下一批。全部完成或明确选择已完成岗位后，再排序、确认目标并保存新结果；旧结果保留。</p>
    {!plan.items.some(i => ["ready", "reuse", "deferred"].includes(i.status)) && <p>当前岗位都需要修复输入或单独模型授权；可以保存等待状态，但不会自动调用模型或生成空推荐。</p>}
    <div className="actions"><button className="button" disabled={busy || !storageReady || (!command && !runnable)} onClick={() => void start()}>{command ? '重试原更新请求' : '启动更新（最多重算 5 个岗位）'}</button>
      {command && <Link className="button secondary" href={runHref(command.body.threadId)}>查看这次更新运行</Link>}
    </div>
    {message && <p role="status">{message}</p>}
    {command && <><p>请求已保留，刷新不会自动执行。核对这次运行后，才可清除请求、另开一次更新。</p>
      <button className="button secondary" disabled={busy || (!rejected && !command)} onClick={() => {
        try {forgetUpdateCommand(window.localStorage, command); setCommand(null); setRejected(false); setMessage('已清除本地请求；服务端历史运行仍保留。');}
        catch {setMessage('请求发生变化，请刷新后核对。');}
      }}>已核对运行，清除本地请求</button></>}
  </section>;
}

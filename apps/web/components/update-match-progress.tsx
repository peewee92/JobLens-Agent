'use client';
import React, {useEffect, useState} from 'react';
import Link from 'next/link';
import type {CareerAgentRunState, UpdateMatchStep} from '@/lib/contracts';
import {clearUpdateBatch, readUpdateBatch, sendUpdateBatch, type UpdateBatchCommand} from '@/lib/update-batch-command';
const labels: Record<UpdateMatchStep['status'], string> = {
  pending: '留待下一批', running: '已领取，若中断可重新计算', completed: '已重算保存', reused: '已复用',
  failed: '本项计算失败，可重试', requires_model: '需要单独模型授权，尚未执行', input_blocked: '需要修复输入',
};
export function UpdateMatchProgress({run, onState, jobTitles = {}}: {run: CareerAgentRunState; jobTitles?: Record<string, string>; onState: (s: CareerAgentRunState) => void}) {
  const [pending, setPending] = useState<UpdateBatchCommand | null>(null);
  const [busy, setBusy] = useState(false), [message, setMessage] = useState(''), [storageReady, setStorageReady] = useState(false);
  useEffect(() => {
    try {setPending(readUpdateBatch(window.localStorage, run.threadId)); setStorageReady(true);}
    catch (e) {setMessage(e instanceof Error ? e.message : '无法读取原分批请求。');}
  }, [run.threadId]);
  const steps = run.updateSteps ?? [], complete = steps.filter(s => ['completed', 'reused'].includes(s.status));
  const active = ['analysis_created', 'update_matching'].includes(run.currentStep) && ['created', 'running'].includes(run.status);
  const retryable = steps.some(s => ['pending', 'running', 'failed'].includes(s.status));
  async function submit(partial: boolean) {
    setBusy(true); setMessage('正在处理明确的这一批，最多尝试 5 个岗位…');
    try {
      const command = readUpdateBatch(window.localStorage, run.threadId) ?? {threadId: run.threadId,
        body: {actionId: `batch-${crypto.randomUUID()}`, expectedRevision: run.revision ?? 0, useCompletedOnly: partial}};
      setPending(command);
      const response = await sendUpdateBatch(window.localStorage, command);
      const body = await response.json();
      if (!response.ok) throw new Error(body.error?.message ?? body.detail ?? '分批执行未返回完整状态，请查看状态或重试原请求。');
      clearUpdateBatch(window.localStorage, command); setPending(null);
      onState(body as CareerAgentRunState); setMessage('已读取本次结果。未完成步骤不会在刷新时自动继续。');
    } catch (e) {setMessage(e instanceof Error ? e.message : '网络未返回状态，请重试原分批请求。');}
    finally {setBusy(false);}
  }
  return <section className="card stack-md" aria-label="逐岗位更新进度"><h2>逐岗位更新进度：{complete.length} / {steps.length}</h2>
    <p>每次明确命令最多尝试 5 个新分析岗位；成功结果独立保留，查看状态不会自动重算或调用模型。</p>
    {run.updatePartial && <p className="notice">你已明确选择只分析完成的岗位，下面未完成项不计入本次结果，不能视为已淘汰。</p>}
    <ul>{steps.map(s => <li key={s.jobId}><Link href={`/jobs/${encodeURIComponent(s.jobId)}`}>{jobTitles[s.jobId] ?? s.jobId}</Link>：{labels[s.status]} · 已尝试 {s.attempt} 次
      {s.errorCode && <span>（{s.errorCode}）</span>}</li>)}</ul>
    {active && <div className="actions">
      <button className="button" disabled={busy || !storageReady || (!pending && !retryable && complete.length !== steps.length)} onClick={() => void submit(false)}>{pending ? '重试原分批请求' : complete.length === steps.length ? '使用已完成报告进入目标确认' : '继续下一批／重试失败项（最多 5 个）'}</button>
      {!pending && complete.length > 0 && complete.length < steps.length && <button className="button secondary" disabled={busy || !storageReady} onClick={() => void submit(true)}>仅使用已完成的 {complete.length} 个岗位进入目标确认</button>}
    </div>}
    {pending && !active && <button className="button" disabled={busy || !storageReady} onClick={() => void submit(false)}>重试原分批请求</button>}
    {pending && <p>原请求已保留。刷新只查看状态；若响应丢失，请重试原分批请求，不要另建命令。</p>}
    {pending && <button className="button secondary" disabled={busy} onClick={() => {
      try {clearUpdateBatch(window.localStorage, pending); setPending(null); setMessage('已清除本地请求，请确认最新状态后再继续。');}
      catch {setMessage('请求已变化，请刷新核对。');}
    }}>已核对服务端状态，清除原分批请求</button>}
    {(run.status === 'stale' || steps.some(s => ['requires_model', 'input_blocked'].includes(s.status))) && run.updateSourceThreadId && <Link href={`/agent/results/${encodeURIComponent(run.updateSourceThreadId)}/update?scope=${run.updateScope ?? 'targets'}`}>修复资料或输入后，返回原范围重新预检；当前步骤不会自行调用模型</Link>}
    {message && <p role="status">{message}</p>}
  </section>;
}

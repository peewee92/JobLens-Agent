'use client';
import React, {useEffect, useState} from 'react';
import {useRouter} from 'next/navigation';
import {workspaceStatusLabels} from '@/lib/workbench';
import {actionStatusLabels} from '@/lib/application-actions';
const statusLabel = (s: string | undefined, fallback: string) => s ? workspaceStatusLabels[s] ?? actionStatusLabels[s] ?? '状态待核实' : fallback;
import {readProgressCommand, progressRaw, discardProgressRaw, sendProgressCommand, type ProgressCommand} from '@/lib/workspace-progress-command';

export function useProgressRequest(workspaceId: string, slot: string) {
  const router = useRouter();
  const [ready,setReady] = useState(false), [busy,setBusy] = useState(false);
  const [original,setOriginal] = useState<ProgressCommand|null>(null), [error,setError] = useState<string|null>(null);
  const [raw,setRaw] = useState<string|null>(null), [broken,setBroken] = useState(false), [reviewed,setReviewed] = useState(false);
  const load = () => {
    try { setRaw(progressRaw(window.localStorage,workspaceId,slot)); setOriginal(readProgressCommand(window.localStorage,workspaceId,slot)); setBroken(false); }
    catch (e) { setBroken(true); setError(e instanceof Error ? e.message : '浏览器请求存储不可用，尚未发送。'); }
    setReady(true);
  };
  useEffect(() => { load(); window.addEventListener('storage',load); return () => window.removeEventListener('storage',load); },[workspaceId,slot]);
  async function send(body: ProgressCommand['body'], retry?: ProgressCommand) {
    setBusy(true); setError(null); setReviewed(false);
    try {
      await sendProgressCommand(window.localStorage,retry ?? {version:1,workspaceId,slot,commandId:crypto.randomUUID(),body});
      router.refresh();
    } catch(e) { setError(e instanceof Error ? e.message : '保存结果未确认，请刷新核对后重试原请求。'); }
    finally { load(); setBusy(false); }
  }
  const recovery = <>
    {(original || broken) && <aside className="notice" aria-label="待确认人工进度请求">
      <p>{broken ? '本地请求无法读取，不能继续发送。' : '有一个人工进度请求尚待核实。刷新只查看，不会自动发送；重试沿用原内容和标识。'}</p>
      {original && <p>原操作：{statusLabel(original.body.expectedStatus,'建立行动')} → {statusLabel(original.body.newStatus,'保存行动清单')}。{original.rejected ? '服务端已拒绝，请核对当前记录。' : '它可能已经保存，不要直接提交另一个操作。'}</p>}
      <div className="actions"><button className="button-secondary" disabled={busy} onClick={() => router.refresh()}>刷新核对服务端记录</button>
        {original && !broken && <button className="button-secondary" disabled={busy} onClick={() => void send(original.body,original)}>重试原人工进度请求</button>}</div>
      <label><input type="checkbox" checked={reviewed} disabled={busy} onChange={e => setReviewed(e.target.checked)} />我已刷新并核对服务端状态与时间线；清除本地请求不会撤销已保存记录</label>
      <button disabled={!reviewed || busy} onClick={() => {
        try { discardProgressRaw(window.localStorage,workspaceId,slot,raw); setOriginal(null); setBroken(false); setError(null); setReviewed(false); load(); }
        catch(e) { setError(e instanceof Error ? e.message : '原请求未清除，请重新核对。'); load(); }
      }}>已核对，结束本次请求恢复</button>
    </aside>}
    {error && <p role="alert" className="error-copy">{error}</p>}
  </>;
  return {send, busy, disabled:!ready || busy || broken || !!original,recovery};
}

"use client";

import {workspaceFetch} from "@/lib/workspace-path";
import Link from "next/link";
import {Button} from "@/components/ui/button";
import {ActionFeedback} from "@/components/ui/patterns";
import {PendingIndicator} from "@/components/ui/pending-indicator";
import {Panel} from "@/components/ui/primitives";
import React, {useEffect, useRef, useState} from "react";
import type {AnalysisExecutionResult} from "@/lib/contracts";
import {readPendingExecution, clearPendingExecution, sendAnalysisExecution, isTerminalStaleExecution, readExecutionResponse, type PendingAnalysisExecution} from "@/lib/analysis-execution";

export function AnalysisExecutionControls({threadId, resultId, jobIds, isCurrent, jobLabels = {}, isUpdate = false}: {
  threadId: string; resultId: string; jobIds: string[]; isCurrent: boolean; jobLabels?: Record<string, string>; isUpdate?: boolean;
}) {
  const writeLock = useRef(false);
  const [loading, setLoading] = useState(true);
  const [execution, setExecution] = useState<AnalysisExecutionResult | null>(null);
  const [pending, setPending] = useState<PendingAnalysisExecution | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [storageError, setStorageError] = useState(false);
  const [staleRejected, setStaleRejected] = useState(false);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const response = await workspaceFetch(`/api/career-agent/runs/${encodeURIComponent(threadId)}/execution`, {cache: "no-store"});
      if (!response.ok) throw new Error("暂时无法读取已保存工作区，请确认连接后再查看。");
      const body = await response.json() as {execution: AnalysisExecutionResult | null};
      setExecution(body.execution);
    } catch (caught) { setError(caught instanceof TypeError || caught instanceof SyntaxError ? "暂时无法读取工作区，请确认连接后再查看。" : caught instanceof Error ? caught.message : "读取工作区失败。"); }
    finally { setLoading(false); }
  }

  useEffect(() => {
    try { setPending(readPendingExecution(window.localStorage, threadId)); }
    catch (caught) { setStorageError(true); setError(caught instanceof Error ? caught.message : "无法保存原请求。"); }
    void load();
    // Each result page binds one immutable thread; GET never starts execution.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [threadId]);

  const existingJobs = new Set(execution?.items.map(item => item.jobId) ?? []);
  const remainingJobs = jobIds.filter(id => !existingJobs.has(id));
  async function start() {
    if (writeLock.current || (!pending && !remainingJobs.length)) return;
    writeLock.current = true;
    setBusy(true); setError(null);
    const command = pending ?? {version: 1 as const, threadId, body: {
      commandId: `execution-${crypto.randomUUID()}`, resultId, jobIds: remainingJobs,
    }};
    setPending(command);
    try {
      const response = await sendAnalysisExecution(window.localStorage, command);
      const body = await readExecutionResponse(response) as AnalysisExecutionResult & {error?: {message?: string}};
      if (!response.ok) {
        if (isTerminalStaleExecution(response.status, body, command)) {
          clearPendingExecution(window.localStorage, command);
          setPending(readPendingExecution(window.localStorage, threadId));
          setStaleRejected(true);
          await load();
          setError("这份分析使用的事实已变化，原请求未建立新材料。请更新分析后再继续。");
          return;
        }
        throw new Error(body.error?.message ?? "执行结果尚未确认，请先查看工作区，再重试原请求。");
      }
      clearPendingExecution(window.localStorage, command);
      setPending(null);
      setExecution(body as AnalysisExecutionResult);
      await load();
    } catch (caught) {
      setError(caught instanceof TypeError ? "连接中断，保存结果尚未确认。请先查看工作区，再重试原请求。" : caught instanceof Error ? caught.message : "执行结果尚未确认。请先查看工作区，再重试原请求。");
    } finally { writeLock.current = false; setBusy(false); }
  }

  return <Panel className="stack-md" aria-label="开始执行分析结果">
    <h2>{isUpdate ? "将新分析用于求职工作区" : "把准备材料变成可跟踪行动"}</h2>
    {isUpdate ? <>
      <p>保存新分析不会自动更改工作区。应用后会建立或复用工作区，并关联新分析及准备材料；已有投递状态、历史材料和行动进度会保留。不会调用模型或自动投递。</p>
      {execution && execution.items.length > 0 && <p>以下岗位曾应用本次分析。若之后应用了其他分析，请进入工作区核对当前关联。</p>}
    </> :
      <p>一次建立或复用目标岗位的工作区，关联这份保存的材料，并建立行动清单。不会调用模型或自动投递。</p>}
    {(!isCurrent || staleRejected) && <p className="notice">这份分析已过期，不能据此建立新材料；已经建立的工作区仍可打开和记录真实进展。</p>}
    {execution && <ul>{execution.items.map(item => <li key={item.jobId}>
      <Link href={`/applications/${encodeURIComponent(item.workspaceId)}`}>打开岗位工作区：{jobLabels[item.jobId] ?? "名称暂不可读取的岗位"}</Link>
      <span className="muted"> · {item.actionIds.length} 项来源行动 · {item.resumeVariantId ? "已保存简历事实草稿" : "证据不足，未制造简历草稿"}</span>
    </li>)}</ul>}
    {pending && !busy && <p className="notice">有一个待核实的原请求。网络重试会沿用同一请求标识和岗位范围，不会重新创建一批工作区。</p>}
    {loading && !busy && <PendingIndicator label={execution ? "正在刷新。已显示的工作区仍保留。" : "正在读取已保存的工作区…"} skeleton={!execution} />}
    {busy && <PendingIndicator label="正在处理本次工作区请求…" slowLabel="仍在等待回执；请不要重复创建。" />}
    <div className="jl-inline">
      {(pending || (isCurrent && !staleRejected && remainingJobs.length > 0)) && <Button aria-busy={busy}
        disabled={busy || loading || storageError || (!pending && (!isCurrent || staleRejected))} onClick={() => void start()}>
        {busy ? "正在保存…" : pending ? "重试原请求" : `${isUpdate ? "应用新分析到工作区" : "创建准备工作区"}（${remainingJobs.length} 个岗位）`}
      </Button>}
      <Button variant="secondary" disabled={busy || loading} onClick={() => {setError(null); void load();}}>查看已保存工作区</Button>
    </div>
    {storageError && !execution && <p className="notice">请允许本页保存原请求后再开始。已有工作区仍可通过服务端查询找回。</p>}
    {error && <ActionFeedback tone="danger">{error}</ActionFeedback>}
    {staleRejected && <Link href={`/agent/results/${encodeURIComponent(threadId)}/update`}>检查输入并更新分析</Link>}
  </Panel>;
}

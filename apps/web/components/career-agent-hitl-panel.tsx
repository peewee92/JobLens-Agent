"use client";

import Link from "next/link";
import {UpdateMatchProgress} from "./update-match-progress";
import {useEffect, useMemo, useState} from "react";

import {
  CareerAgentRunHttpError,
  buildGapHandoffHref,
  shouldForgetPendingThread,
  targetSelectionBlockMessage,
} from "@/lib/career-agent-run";
import {
  clearRunCommand, commandResolution, loadRunCommand, runHref, saveRunCommand,
  sendRunCommand, validThreadReference, type SavedRunCommand,
} from "@/lib/career-agent-commands";
import {userFacingApiError} from "@/lib/user-facing-errors";
import type {ApiErrorBody, JobListItem, CareerAgentRunState as RunState} from "@/lib/contracts";

type Decision = "approve" | "edit" | "reject";
const RUN_STATUS_LABELS: Record<string, string> = {
  created: "已保存输入", running: "分析待继续", interrupted: "等待确认", resuming: "分析待继续",
  completed: "已完成", cancelled: "已结束", blocked: "需要补齐输入", failed: "执行失败", stale: "资料已变化",
};
const STORAGE_KEY = "joblens.careerAgent.pendingThread";

function newId(prefix: string): string {
  return `${prefix}-${crypto.randomUUID()}`;
}

async function parseResponse(response: Response): Promise<RunState> {
  if (response.ok) return (await response.json()) as RunState;
  let message = `请求失败（${response.status}）`;
  try {
    const body = (await response.json()) as ApiErrorBody | {detail?: string};
    if ("error" in body) message = userFacingApiError(body, message);
    else if (typeof body.detail === "string") message = body.detail;
  } catch {}
  throw new CareerAgentRunHttpError(response.status, message);
}

export function CareerAgentHitlPanel({jobs}: {jobs: JobListItem[]}) {
  const [selected, setSelected] = useState<string[]>(() => jobs.slice(0, 5).map((job) => job.id));
  const [edited, setEdited] = useState<string[]>([]);
  const [run, setRun] = useState<RunState | null>(null);
  const [recoverableThreadId, setRecoverableThreadId] = useState<string | null>(null);
  const [pendingCommand, setPendingCommand] = useState<SavedRunCommand | null>(null);
  const [recentRuns, setRecentRuns] = useState<RunState[]>([]);
  const [recentError, setRecentError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("选择已有匹配结果的岗位，然后让 Agent 给出目标岗位建议。");
  const jobsById = useMemo(() => new Map(jobs.map((job) => [job.id, job])), [jobs]);

  useEffect(() => {
    void loadRecentRuns();
    const fromUrl = new URLSearchParams(window.location.search).get("threadId");
    let local: string | null = null;
    try { local = window.localStorage.getItem(STORAGE_KEY); } catch {}
    const threadId = validThreadReference(fromUrl) ? fromUrl : validThreadReference(local) ? local : null;
    if (!threadId) return;
    setRecoverableThreadId(threadId);
    try {
      const command = loadRunCommand(window.localStorage, threadId);
      setPendingCommand(command);
      if (command?.kind === "start") setSelected(command.body.jobIds);
    } catch {}
    void recoverRun(threadId);
  }, []);

  async function loadRecentRuns() {
    try {
      const response = await fetch("/api/career-agent/runs?limit=10", {cache: "no-store"});
      if (!response.ok) throw new Error("暂时无法读取最近分析，请重试。已有分析不会因此丢失。");
      const body = await response.json() as {items: RunState[]};
      setRecentRuns(body.items);
      setRecentError(null);
    } catch (error) {
      setRecentError(error instanceof Error ? error.message : "暂时无法读取最近分析。");
    }
  }

  function rememberThread(threadId: string) {
    window.history.replaceState(null, "", runHref(threadId));
    try { window.localStorage.setItem(STORAGE_KEY, threadId); } catch {}
  }

  function displayState(state: RunState) {
    setRun(state);
    setEdited(state.proposedTargetJobIds);
    setRecoverableThreadId(null);
    rememberThread(state.threadId);
    let resolution: "accepted" | "superseded" | "pending" = "pending";
    try {
      const command = loadRunCommand(window.localStorage, state.threadId);
      if (command) resolution = commandResolution(command, state);
      if (command && resolution !== "pending") {
        clearRunCommand(window.localStorage, command);
        setPendingCommand(null);
      } else setPendingCommand(command);
    } catch {
      setPendingCommand(null); // Server state and the URL still permit recovery.
    }
    void loadRecentRuns();
    return resolution;
  }

  async function recoverRun(threadId: string) {
    setBusy(true);
    setMessage("正在恢复上次 Agent Run…");
    try {
      const state = await parseResponse(
        await fetch(`/api/career-agent/runs/${encodeURIComponent(threadId)}`, {cache: "no-store"}),
      );
      const resolution = displayState(state);
      setMessage(resolution === "superseded" ? "另一个页面已提交不同决定，当前显示服务端已接受的结果，原请求不会再重试。" : state.pendingApproval ? "已恢复上次等待你确认的 Agent Run。" : targetSelectionBlockMessage(state.currentStep) ?? "已恢复上次 Agent Run。");
    } catch (error) {
      let saved: SavedRunCommand | null = null;
      try { saved = loadRunCommand(window.localStorage, threadId); } catch {}
      if (shouldForgetPendingThread(error) && saved?.kind !== "start") {
        try { window.localStorage.removeItem(STORAGE_KEY); } catch {}
        setRecoverableThreadId(null);
        setMessage("上次 Agent Run 已不存在，可以开始新的 Run。");
      } else {
        setRecoverableThreadId(threadId);
        setPendingCommand(saved);
        setMessage(saved?.kind === "start" && shouldForgetPendingThread(error)
          ? "服务端尚未找到这次分析。原请求已保留，可以用相同标识重试，不会新建另一次分析。"
          : "暂时无法恢复上次 Agent Run。恢复引用已保留，请重试，不会重新启动 Ranking。");
      }
    } finally {
      setBusy(false);
    }
  }

  async function submitSavedCommand(command: SavedRunCommand) {
    setBusy(true);
    setMessage(command.kind === "start" ? "正在读取现有匹配报告并排序…" : "正在提交已保存的决定并校验事实…");
    try {
      saveRunCommand(window.localStorage, command);
      setPendingCommand(command);
      rememberThread(command.threadId);
      if (!run) setRecoverableThreadId(command.threadId);
      const state = await parseResponse(await sendRunCommand(window.localStorage, command));
      displayState(state);
      setMessage(state.pendingApproval ? "Agent 已暂停，等待你确认目标岗位。" :
        state.status === "completed" ? "能力差距分析已完成。" :
        state.status === "cancelled" ? "你已拒绝这组目标岗位，本次分析已结束。" :
        state.status === "stale" ? "职业事实已变化，本次分析已安全停止，请新建分析。" :
        targetSelectionBlockMessage(state.currentStep) ?? "分析状态已更新。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "暂时无法提交；原请求已保留，请先查看状态或重试原请求。");
    } finally { setBusy(false); }
  }

  async function startRun() {
    if (selected.length === 0 || pendingCommand) return;
    const threadId = newId("thread");
    await submitSavedCommand({version: 1, kind: "start", threadId, body: {
      threadId, runId: newId("run"), requestId: newId("request"),
      jobIds: [...selected], topN: Math.min(3, selected.length),
    }});
  }

  async function decide(decision: Decision) {
    if (!run?.interruptId || pendingCommand) return;
    await submitSavedCommand({version: 1, kind: "decision", threadId: run.threadId, body: {
      interruptId: run.interruptId, actionId: newId("action"), decision,
      selectedJobIds: decision === "edit" ? [...edited] : [],
    }});
  }

  async function continueRun() {
    if (!run) return;
    setBusy(true);
    setMessage("正在继续已保存的分析，不会重新提交人工决定…");
    try {
      const state = await parseResponse(await fetch(
        `/api/career-agent/runs/${encodeURIComponent(run.threadId)}/continue`,
        {method: "POST"},
      ));
      displayState(state);
      setMessage(state.pendingApproval ? "分析已恢复，请确认目标岗位。" :
        state.status === "completed" ? "本次分析已完成。" :
        state.status === "stale" ? "资料已经变化，请保留旧结果并新建分析。" :
        targetSelectionBlockMessage(state.currentStep) ?? "分析状态已更新。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "暂时无法继续，请先重新查看状态。");
    } finally {
      setBusy(false);
    }
  }

  const gapHandoffHref = run?.status === "completed" && !run.legacyReadOnly
    ? buildGapHandoffHref(run.confirmedTargetJobIds)
    : null;
  const activeJobIds = run?.requestedJobIds ?? selected;
  const activeJobNames = activeJobIds.map((id) => jobsById.get(id)?.title ?? id);
  const requestSummary = activeJobNames.length > 0
    ? `帮我先比较这 ${activeJobNames.length} 个岗位，找出最值得优先考虑的岗位，再分析共同能力差距。`
    : "帮我比较目标岗位并分析共同能力差距。";
  const planSummary = run?.pendingApproval
    ? "已完成岗位排序；下一步需要你确认目标岗位，然后才会分析共同能力差距。"
    : run?.status === "completed"
      ? run.updatePartial ? "已保存部分范围的目标分析；未完成岗位仍明确列出，不代表已淘汰。" : "岗位排序 → 人工确认 → 能力差距分析已完成。"
      : run?.currentStep === "update_matching"
        ? "已按固定事实处理当前小批；请查看逐岗位结果，明确继续下一批或仅使用已完成岗位。"
      : run
        ? `当前步骤：${run.currentStep}。系统只会沿已受治理的 Ranking → 人工确认 → Skill Gap 路径执行。`
        : "选择岗位后，系统会先读取已有匹配结果并排序；目标岗位必须由你确认后才继续能力差距分析。";

  return (
    <div className="stack-lg">
      <section className="card stack-md" aria-label="Career Agent Chat">
        <div>
          <p className="eyebrow">Career Agent Chat</p>
          <h2>受治理的求职分析对话</h2>
          <p className="muted">当前界面只展示已经接通并通过持久化验证的 Agent 路径；自由文本意图模型仍受 Release Gate 管理，不会在这里伪装成已上线能力。</p>
        </div>
        <div className="stack-sm">
          <div>
            <strong>你的请求</strong>
            <p>{requestSummary}</p>
          </div>
          <div>
            <strong>当前计划</strong>
            <p>{planSummary}</p>
          </div>
          <div>
            <strong>执行状态</strong>
            <p role="status">{message}</p>
          </div>
          <details>
            <summary>查看依据</summary>
            <p className="muted">本流程只读取已有 MatchReport，并沿同一套 JobRequirement / Profile Evidence 事实继续分析，不重新猜测简历或岗位事实。</p>
            {activeJobNames.length > 0 && <p className="muted">当前岗位范围：{activeJobNames.join("、")}</p>}
            {run?.updateSourceThreadId && <p>这是基于历史结果创建的独立更新，原结果不会被覆盖。<Link href={`/agent/results/${encodeURIComponent(run.updateSourceThreadId)}`}>查看原分析</Link></p>}
            {run?.gapResultFingerprint && <p className="muted">能力差距结果指纹：{run.gapResultFingerprint}</p>}
          </details>
        </div>
      </section>
      {!!run?.updateSteps?.length && <UpdateMatchProgress key={run.threadId} run={run} jobTitles={Object.fromEntries(jobs.map(j => [j.id, j.title]))} onState={state => {
        displayState(state);
        setMessage(state.pendingApproval ? "岗位排序已完成，请确认目标岗位。" : targetSelectionBlockMessage(state.currentStep) ?? "本次处理已保存，请查看当前状态。");
      }} />}
      {pendingCommand && (
        <section className="card stack-md" aria-label="未确认请求">
          <h2>这次请求的结果尚未确认</h2>
          <p>原岗位范围和决定已保存。请先查看服务端状态；需要重试时会沿用原标识和原内容，不会改成另一决定。</p>
          <p className="muted">{pendingCommand.kind === "start"
            ? `原请求：分析 ${pendingCommand.body.jobIds.map((id) => jobsById.get(id)?.title ?? id).join("、")}；最多建议 ${pendingCommand.body.topN} 个目标。`
            : `原决定：${pendingCommand.body.decision === "approve" ? "确认建议" : pendingCommand.body.decision === "reject" ? "拒绝并结束" : `确认所选 ${pendingCommand.body.selectedJobIds.length} 个目标`}。`}</p>
          <div className="button-row">
            <button className="button primary" disabled={busy} onClick={() => void recoverRun(pendingCommand.threadId)} type="button">查看请求状态</button>
            <button className="button" disabled={busy} onClick={() => void submitSavedCommand(pendingCommand)} type="button">重试原请求</button>
          </div>
        </section>
      )}

      {!run && recoverableThreadId && (
        <section className="card stack-md">
          <div>
            <p className="eyebrow">恢复已有 Run</p>
            <h2>上次 Agent Run 仍可恢复</h2>
            <p className="muted">刚才可能只是网络或服务暂时不可用。JobLens 已保留 durable thread 引用，不会因为一次恢复失败就重新 Ranking。</p>
          </div>
          <div className="button-row">
            <button className="button primary" disabled={busy} onClick={() => void recoverRun(recoverableThreadId)} type="button">
              {busy ? "正在恢复…" : "重试恢复"}
            </button>
            <button
              className="button"
              disabled={busy}
              onClick={() => {
                try { window.localStorage.removeItem(STORAGE_KEY); } catch {}
                window.history.replaceState(null, "", "/agent");
                setPendingCommand(null);
                setRecoverableThreadId(null);
                setMessage("已放弃本地旧 Run 引用，可以开始新的 Agent Run。");
              }}
              type="button"
            >
              放弃旧 Run
            </button>
          </div>
        </section>
      )}

      {!run && !recoverableThreadId && (
        <section className="card stack-md">
          <div>
            <p className="eyebrow">Step 1 · 选择岗位</p>
            <h2>选择要一起分析的岗位</h2>
            <p className="muted">一次最多比较 50 个岗位，只读取已有匹配报告；默认建议最多 3 个目标，不会重新调用模型或自动修改职业事实。</p>
          </div>
          <div className="stack-sm">
            {jobs.map((job) => (
              <label className="check-row" key={job.id}>
                <input
                  type="checkbox"
                  checked={selected.includes(job.id)}
                  onChange={(event) => setSelected((current) => event.target.checked
                    ? Array.from(new Set([...current, job.id])).slice(0, 50)
                    : current.filter((id) => id !== job.id))}
                />
                <span><strong>{job.title}</strong> · {job.company}</span>
              </label>
            ))}
          </div>
          <button className="button primary" disabled={busy || selected.length === 0} onClick={startRun} type="button">
            {busy ? "正在运行…" : `运行 Agent（${selected.length} 个岗位）`}
          </button>
        </section>
      )}

      {run && !run.legacyReadOnly && !(run.updateSteps?.length && ["analysis_created", "update_matching"].includes(run.currentStep)) && ["created", "running", "resuming"].includes(run.status) && (
        <section className="card stack-md">
          <h2>继续已保存的分析</h2>
          <p className="muted">刷新只查看状态，不会自动执行。若前次请求中断，可显式继续；仍在执行的请求会受到保护，不会并行推进。</p>
          <div className="button-row">
            <button className="button primary" disabled={busy} onClick={() => void continueRun()} type="button">继续分析</button>
            <button className="button" disabled={busy} onClick={() => void recoverRun(run.threadId)} type="button">重新查看状态</button>
          </div>
        </section>
      )}

      {run?.pendingApproval && (
        <section className="card stack-md">
          <div>
            <p className="eyebrow">Step 2 · 需要你的决定</p>
            <h2>确认目标岗位集合</h2>
            <p className="muted">默认建议最多 3 个；你可调整并确认最多 5 个。只有确认后才会继续能力差距分析，不能直接选择没有有效报告的岗位。</p>
            {run.targetSuggestionMode === "challenge_only" ? <p className="notice">本次只有挑战／待核实目标，没有优先投入建议。相关基础不代表条件已全部满足，请先查看关键未知。</p> : null}
            <Link href="/recommendations">核对分组、证据和关键未知</Link>
          </div>
          <div className="stack-sm">
            {run.rankedJobIds.map((jobId) => {
              const job = jobsById.get(jobId);
              return (
                <label className="check-row" key={jobId}>
                  <input
                    type="checkbox"
                    checked={edited.includes(jobId)}
                    disabled={!edited.includes(jobId) && edited.length >= 5}
                    onChange={(event) => setEdited((current) => event.target.checked
                      ? Array.from(new Set([...current, jobId])).slice(0, 5)
                      : current.filter((id) => id !== jobId))}
                  />
                  <span>{job ? <><strong>{job.title}</strong> · {job.company}</> : jobId}{!run.proposedTargetJobIds.includes(jobId) ? " · 非默认建议，请先核对证据与未知" : ""}</span>
                </label>
              );
            })}
          </div>
          <div className="button-row">
            <button className="button primary" disabled={busy || !!pendingCommand} onClick={() => decide("approve")} type="button">直接确认建议</button>
            <button className="button" disabled={busy || !!pendingCommand || edited.length === 0} onClick={() => decide("edit")} type="button">按当前勾选继续</button>
            <button className="button" disabled={busy || !!pendingCommand} onClick={() => decide("reject")} type="button">拒绝并结束</button>
          </div>
        </section>
      )}

      {run && !run.pendingApproval && !["created", "running", "resuming"].includes(run.status) && (
        <section className="card stack-md">
          <p className="eyebrow">Run 状态 · {run.status}</p>
          <h2>{run.status === "completed" ? run.updatePartial ? "已保存部分范围的能力差距分析" : "Agent 已完成能力差距分析" : "Agent Run 已结束或暂停"}</h2>
          <p>{message}</p>
          {run.currentStep === "analysis_facts_changed" ? <p className="notice">分析期间资料、意向或岗位事实发生变化。本次材料如已保存，仅供历史查看；请使用当前事实新建分析。</p> : null}
          {run.legacyReadOnly ? <p className="notice">旧运行仅供历史查看。旧结果没有保存可重开的原始分析快照，未完成的旧运行也不会按新规则继续；请开始新分析。</p> : null}
          {run.status === "blocked" ? <div className="actions">
            <Link href="/recommendations">查看分类和逐项原因</Link>
            <Link href="/profile">核实职业资料与求职意向</Link>
          </div> : null}
          {run.confirmedTargetJobIds.length > 0 && <p className="muted">已确认目标岗位：{run.confirmedTargetJobIds.map((id) => jobsById.get(id)?.title ?? id).join("、")}</p>}
          {run.gapResultFingerprint && !run.resultId && <p className="muted">已保存本次分析指纹，完整结果快照尚未保存（{run.gapResultFingerprint.slice(0, 12)}…）。</p>}
          {run.resultId ? <div className="actions">
            <Link className="button primary" href={`/agent/results/${encodeURIComponent(run.threadId)}`}>打开已保存的分析与准备材料</Link>
            <p className="muted">查看本次事实版本下的原始结果，不会重新计算或调用模型。</p>
          </div> : null}
          {gapHandoffHref && !run.resultId && (
            <div className="actions">
              <Link className="button primary" href={gapHandoffHref}>按当前资料查看能力差距</Link>
              <p className="muted">已确认的目标岗位会直接带入现有能力差距工作区，由同一套 JobRequirement / Profile Evidence 规则展示 P0/P1、影响岗位和补齐标准。</p>
            </div>
          )}
          <button className="button" type="button" onClick={() => {setRun(null); setPendingCommand(null); window.history.replaceState(null, "", "/agent"); try { window.localStorage.removeItem(STORAGE_KEY); } catch {} setMessage("可以开始新的 Agent Run。");}}>开始新的 Run</button>
        </section>
      )}

      <section className="card stack-md" aria-label="最近分析">
        <h2>最近分析</h2>
        <p className="muted">从服务端读取已保存的运行；打开只查看状态，不会自动继续分析。旧独立检查点文件不在此列表中。</p>
        {recentError ? <p role="alert">{recentError}</p> : null}
        <button className="button" disabled={busy} onClick={() => void loadRecentRuns()} type="button">刷新最近分析</button>
        {recentRuns.length === 0 && !recentError ? <p>暂无已保存分析。</p> : null}
        <ul>{recentRuns.map((item) => <li key={item.threadId}>
          <a href={runHref(item.threadId)}>{item.requestedJobIds.length} 个岗位 · {item.updatePartial ? "部分范围已保存" : RUN_STATUS_LABELS[item.status] ?? "已保存"} · {item.threadId.slice(-8)}</a>
        </li>)}</ul>
      </section>

      <p className="muted" role="status">{message}</p>
    </div>
  );
}

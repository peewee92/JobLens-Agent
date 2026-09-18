"use client";

import Link from "next/link";
import {useEffect, useMemo, useState} from "react";

import {
  CareerAgentRunHttpError,
  buildGapHandoffHref,
  shouldForgetPendingThread,
} from "@/lib/career-agent-run";
import type {JobListItem} from "@/lib/contracts";

type RunState = {
  threadId: string;
  runId: string;
  status: "created" | "running" | "interrupted" | "resuming" | "completed" | "cancelled" | "blocked" | "failed" | "stale";
  currentStep: string;
  requestedJobIds: string[];
  rankedJobIds: string[];
  proposedTargetJobIds: string[];
  confirmedTargetJobIds: string[];
  pendingApproval: boolean;
  interruptId: string | null;
  humanDecision: string | null;
  gapResultFingerprint: string | null;
};

type Decision = "approve" | "edit" | "reject";
const STORAGE_KEY = "joblens.careerAgent.pendingThread";

function newId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

async function parseResponse(response: Response): Promise<RunState> {
  if (response.ok) return (await response.json()) as RunState;
  let message = `请求失败（${response.status}）`;
  try {
    const body = (await response.json()) as {detail?: string};
    if (body.detail) message = body.detail;
  } catch {}
  throw new CareerAgentRunHttpError(response.status, message);
}

export function CareerAgentHitlPanel({jobs}: {jobs: JobListItem[]}) {
  const [selected, setSelected] = useState<string[]>(() => jobs.slice(0, 5).map((job) => job.id));
  const [edited, setEdited] = useState<string[]>([]);
  const [run, setRun] = useState<RunState | null>(null);
  const [recoverableThreadId, setRecoverableThreadId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("选择已有匹配结果的岗位，然后让 Agent 给出目标岗位建议。");
  const jobsById = useMemo(() => new Map(jobs.map((job) => [job.id, job])), [jobs]);

  useEffect(() => {
    const threadId = window.localStorage.getItem(STORAGE_KEY);
    if (!threadId) return;
    setRecoverableThreadId(threadId);
    void recoverRun(threadId);
  }, []);

  async function recoverRun(threadId: string) {
    setBusy(true);
    setMessage("正在恢复上次 Agent Run…");
    try {
      const state = await parseResponse(
        await fetch(`/api/career-agent/runs/${encodeURIComponent(threadId)}`, {cache: "no-store"}),
      );
      setRun(state);
      setEdited(state.proposedTargetJobIds);
      setRecoverableThreadId(null);
      if (["completed", "cancelled", "blocked", "failed", "stale"].includes(state.status)) {
        window.localStorage.removeItem(STORAGE_KEY);
      }
      setMessage(state.pendingApproval ? "已恢复上次等待你确认的 Agent Run。" : "已恢复上次 Agent Run。");
    } catch (error) {
      if (shouldForgetPendingThread(error)) {
        window.localStorage.removeItem(STORAGE_KEY);
        setRecoverableThreadId(null);
        setMessage("上次 Agent Run 已不存在，可以开始新的 Run。");
      } else {
        setRecoverableThreadId(threadId);
        setMessage("暂时无法恢复上次 Agent Run。恢复引用已保留，请重试，不会重新启动 Ranking。");
      }
    } finally {
      setBusy(false);
    }
  }

  async function startRun() {
    if (selected.length === 0) return;
    setBusy(true);
    setMessage("正在读取现有 MatchReport 并排序…");
    const threadId = newId("thread");
    try {
      const state = await parseResponse(await fetch("/api/career-agent/runs", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          threadId,
          runId: newId("run"),
          requestId: newId("request"),
          jobIds: selected,
          topN: Math.min(5, selected.length),
        }),
      }));
      window.localStorage.setItem(STORAGE_KEY, threadId);
      setRecoverableThreadId(null);
      setRun(state);
      setEdited(state.proposedTargetJobIds);
      setMessage(state.pendingApproval ? "Agent 已暂停，等待你确认目标岗位。" : "Agent Run 已更新。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "无法启动 Agent Run。");
    } finally {
      setBusy(false);
    }
  }

  async function decide(decision: Decision) {
    if (!run?.interruptId) return;
    setBusy(true);
    setMessage(decision === "reject" ? "正在结束本次 Run…" : "正在校验最新事实并继续能力差距分析…");
    try {
      const state = await parseResponse(await fetch(
        `/api/career-agent/runs/${encodeURIComponent(run.threadId)}/resume`,
        {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({
            interruptId: run.interruptId,
            actionId: newId("action"),
            decision,
            selectedJobIds: decision === "edit" ? edited : [],
          }),
        },
      ));
      setRun(state);
      if (["completed", "cancelled", "blocked", "failed", "stale"].includes(state.status)) {
        window.localStorage.removeItem(STORAGE_KEY);
      }
      setMessage(
        state.status === "completed" ? "能力差距分析已完成。" :
        state.status === "stale" ? "暂停期间职业事实发生变化，本次旧 Run 已安全停止，请重新运行。" :
        state.status === "cancelled" ? "你已拒绝这组目标岗位，本次 Run 已结束。" :
        state.status === "blocked" ? "当前事实还不足以继续，本次 Run 已安全阻止。" :
        "Agent Run 已更新。",
      );
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "无法继续 Agent Run。");
    } finally {
      setBusy(false);
    }
  }

  const gapHandoffHref = run?.status === "completed"
    ? buildGapHandoffHref(run.confirmedTargetJobIds)
    : null;

  return (
    <div className="stack-lg">
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
                window.localStorage.removeItem(STORAGE_KEY);
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
            <p className="muted">本阶段只读取已有 MatchReport，不会重新调用模型或自动修改你的职业事实。</p>
          </div>
          <div className="stack-sm">
            {jobs.map((job) => (
              <label className="check-row" key={job.id}>
                <input
                  type="checkbox"
                  checked={selected.includes(job.id)}
                  onChange={(event) => setSelected((current) => event.target.checked
                    ? Array.from(new Set([...current, job.id])).slice(0, 10)
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

      {run?.pendingApproval && (
        <section className="card stack-md">
          <div>
            <p className="eyebrow">Step 2 · 需要你的决定</p>
            <h2>确认目标岗位集合</h2>
            <p className="muted">Agent 已根据现有 Ranking 提议以下岗位。只有你确认后才会继续 Skill Gap。</p>
          </div>
          <div className="stack-sm">
            {run.requestedJobIds.map((jobId) => {
              const job = jobsById.get(jobId);
              return (
                <label className="check-row" key={jobId}>
                  <input
                    type="checkbox"
                    checked={edited.includes(jobId)}
                    onChange={(event) => setEdited((current) => event.target.checked
                      ? Array.from(new Set([...current, jobId])).slice(0, 10)
                      : current.filter((id) => id !== jobId))}
                  />
                  <span>{job ? <><strong>{job.title}</strong> · {job.company}</> : jobId}</span>
                </label>
              );
            })}
          </div>
          <div className="button-row">
            <button className="button primary" disabled={busy} onClick={() => decide("approve")} type="button">直接确认建议</button>
            <button className="button" disabled={busy || edited.length === 0} onClick={() => decide("edit")} type="button">按当前勾选继续</button>
            <button className="button" disabled={busy} onClick={() => decide("reject")} type="button">拒绝并结束</button>
          </div>
        </section>
      )}

      {run && !run.pendingApproval && (
        <section className="card stack-md">
          <p className="eyebrow">Run 状态 · {run.status}</p>
          <h2>{run.status === "completed" ? "Agent 已完成能力差距分析" : "Agent Run 已结束或暂停"}</h2>
          <p>{message}</p>
          {run.confirmedTargetJobIds.length > 0 && <p className="muted">已确认目标岗位：{run.confirmedTargetJobIds.map((id) => jobsById.get(id)?.title ?? id).join("、")}</p>}
          {run.gapResultFingerprint && <p className="muted">Gap 结果已持久化并可追踪（{run.gapResultFingerprint.slice(0, 12)}…）。</p>}
          {gapHandoffHref && (
            <div className="actions">
              <Link className="button primary" href={gapHandoffHref}>查看能力差距结果</Link>
              <p className="muted">已确认的目标岗位会直接带入现有能力差距工作区，由同一套 JobRequirement / Profile Evidence 规则展示 P0/P1、影响岗位和补齐标准。</p>
            </div>
          )}
          <button className="button" type="button" onClick={() => {setRun(null); setMessage("可以开始新的 Agent Run。");}}>开始新的 Run</button>
        </section>
      )}

      <p className="muted" role="status">{message}</p>
    </div>
  );
}

"use client";
import {workspaceFetch, workspacePath} from "@/lib/workspace-path";
import {Pagination} from "@/components/ui/pagination";
import {PendingIndicator} from "@/components/ui/pending-indicator";
import {Button} from "@/components/ui/button";
import {ActionFeedback} from "@/components/ui/patterns";
import {Callout, Panel} from "@/components/ui/primitives";
import {RankedJobExplanation} from "@/components/ranked-job-explanation";

import {validatedRunLabels} from "@/lib/agent-run-labels";
import {UnrankedJobs} from "@/components/unranked-jobs";
import {appendAgentJobPage} from "@/lib/agent-job-pages";
import {rankingOmissionMessage, rankingPreflight, rankingRecoveryAnchor, rankingScope, type RankingPreflight} from "@/lib/agent-ranking-preflight";

import Link from "next/link";
import {LinkFeedback} from "@/components/link-feedback";
import {agentScopeHref, initialAgentJobScope, jobDetailWithAgentScope, initialScopeAnalysisHref} from "@/lib/agent-job-scope";
import {UpdateMatchProgress} from "./update-match-progress";
import {useEffect, useMemo, useRef, useState} from "react";

import {
  CareerAgentRunHttpError,
  careerAgentStepSummary,
  buildGapHandoffHref,
  shouldForgetPendingThread,
  targetSelectionBlockMessage,
} from "@/lib/career-agent-run";
import {
  clearRunCommand, commandResolution, hasRunCommandRecord, loadRunCommand, rankedReportHref, runHref, saveRunCommand,
  sendRunCommand, validThreadReference, type SavedRunCommand,
} from "@/lib/career-agent-commands";
import {userFacingApiError} from "@/lib/user-facing-errors";
import type {ApiErrorBody, JobListItem, CareerAgentRunState as RunState} from "@/lib/contracts";

type Decision = "approve" | "edit" | "reject";
const RUN_STATUS_LABELS: Record<string, string> = {
  created: "已保存输入", running: "分析待继续", interrupted: "等待确认", resuming: "分析待继续",
  completed: "已完成", cancelled: "已结束", blocked: "需要补齐输入", failed: "执行失败", stale: "分析依据已变化",
};
const PAGE_SIZE = 20;
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

export function RankedJobLabel({job, label}: {job?: JobListItem; label?: string; jobId: string}) {
  return job ? <><strong>{job.title}</strong> · {job.company}</> : <>{label ?? "岗位名称暂不可读取"}</>;
}

export function CareerAgentHitlPanel({jobs: initialJobs, initialJobId, initialScope, initialPageOffset = 0, initialHasMore = false}: {jobs: JobListItem[]; initialJobId?: string; initialScope?: string[]; initialPageOffset?: number; initialHasMore?: boolean}) {
  const pageLock = useRef(false);
  const commandLock = useRef(false);
  const checkLock = useRef(false);
  const [jobs, setJobs] = useState(initialJobs);
  const [visibleOffset, setVisibleOffset] = useState(0);
  const pageJobs = jobs.slice(visibleOffset, visibleOffset + PAGE_SIZE);
  const [pageOffset, setPageOffset] = useState(initialPageOffset);
  const [hasMore, setHasMore] = useState(initialHasMore);
  const [loadingJobs, setLoadingJobs] = useState(false);
  const [jobPageError, setJobPageError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string[]>(() => initialAgentJobScope(jobs.map(job => job.id), initialScope ?? initialJobId));
  const [preflight, setPreflight] = useState<RankingPreflight | null>(null);
  const [checking, setChecking] = useState(false);
  const [preflightError, setPreflightError] = useState<{scope: string; message: string} | null>(null);
  const [edited, setEdited] = useState<string[]>([]);
  const [run, setRun] = useState<RunState | null>(null);
  const [runLabels, setRunLabels] = useState<Record<string, string>>({});
  const [recoverableThreadId, setRecoverableThreadId] = useState<string | null>(null);
  const [pendingCommand, setPendingCommand] = useState<SavedRunCommand | null>(null);
  const [recentRuns, setRecentRuns] = useState<RunState[]>([]);
  const [recentError, setRecentError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("选择已有报告的岗位，检查后查看建议与依据。");
  const jobsById = useMemo(() => new Map(jobs.map((job) => [job.id, job])), [jobs]);
  const currentScope = rankingScope(selected);
  const currentPreflight = preflight?.scope === currentScope ? preflight : null;
  const rankableCount = currentPreflight?.ranked.length;
  const compareButtonLabel = rankableCount === undefined ? "检查后开始比较"
    : rankableCount === 0 ? "没有可比较的岗位" : `比较 ${rankableCount} 个岗位`;

  useEffect(() => {
    void loadRecentRuns();
    const fromUrl = new URLSearchParams(window.location.search).get("threadId");
    let local: string | null = null;
    try { local = window.localStorage.getItem(STORAGE_KEY); } catch {}
    // An explicit job scope wins over an old local run, but never hide an unresolved command.
    let localCommand = false;
    let localCommandChecked = false;
    if (validThreadReference(local)) {
      try { localCommand = hasRunCommandRecord(window.localStorage, local); localCommandChecked = true; } catch {}
    }
    const explicitScope = initialScope !== undefined || initialJobId !== undefined;
    const threadId = validThreadReference(fromUrl) ? fromUrl :
      validThreadReference(local) && (!explicitScope || !localCommandChecked || localCommand) ? local : null;
    if (!threadId) return;
    setRecoverableThreadId(threadId);
    try {
      const command = loadRunCommand(window.localStorage, threadId);
      setPendingCommand(command);
      if (command?.kind === "start") setSelected(command.body.jobIds);
    } catch {}
    void recoverRun(threadId);
  }, []);

  const runLabelScope = run?.requestedJobIds.join("\u0000") ?? "";
  useEffect(() => {
    if (!runLabelScope) { setRunLabels({}); return; }
    const ids = runLabelScope.split("\u0000");
    const query = new URLSearchParams();
    ids.forEach(id => query.append("jobId", id));
    let cancelled = false;
    setRunLabels({});
    void workspaceFetch(`/api/jobs/labels?${query}`, {cache: "no-store"})
      .then(response => response.ok ? response.json() : null)
      .then(body => { if (!cancelled) setRunLabels(validatedRunLabels(ids, body)); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [runLabelScope]);

  async function loadRecentRuns() {
    try {
      const response = await workspaceFetch("/api/career-agent/runs?limit=10", {cache: "no-store"});
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
    setMessage("正在恢复上次比较…");
    try {
      const state = await parseResponse(
        await workspaceFetch(`/api/career-agent/runs/${encodeURIComponent(threadId)}`, {cache: "no-store"}),
      );
      const resolution = displayState(state);
      setMessage(resolution === "superseded" ? "另一个页面已提交不同决定，当前显示服务端已接受的结果，原请求不会再重试。" : state.pendingApproval ? "已恢复上次等待你确认的 比较。" : targetSelectionBlockMessage(state.currentStep) ?? "已恢复上次比较。");
    } catch (error) {
      let saved: SavedRunCommand | null = null;
      try { saved = loadRunCommand(window.localStorage, threadId); } catch {}
      if (shouldForgetPendingThread(error) && saved?.kind !== "start") {
        try { window.localStorage.removeItem(STORAGE_KEY); } catch {}
        setRecoverableThreadId(null);
        setMessage("上次比较 已不存在，可以开始新的比较。");
      } else {
        setRecoverableThreadId(threadId);
        setPendingCommand(saved);
        setMessage(saved?.kind === "start" && shouldForgetPendingThread(error)
          ? "服务端尚未找到这次分析。原请求已保留，可以用相同标识重试，不会新建另一次分析。"
          : "暂时无法恢复上次比较。恢复引用已保留，请重试，不会重新启动比较。");
      }
    } finally {
      setBusy(false);
    }
  }

  async function submitSavedCommand(command: SavedRunCommand) {
    if (commandLock.current) return;
    commandLock.current = true;
    setBusy(true);
    setMessage(command.kind === "start" ? "正在读取现有匹配报告并排序…" : "正在提交已保存的决定并校验事实…");
    try {
      saveRunCommand(window.localStorage, command);
      setPendingCommand(command);
      rememberThread(command.threadId);
      if (!run) setRecoverableThreadId(command.threadId);
      const state = await parseResponse(await sendRunCommand(window.localStorage, command));
      displayState(state);
      setMessage(state.pendingApproval ? "比较已完成，请确认准备目标。" :
        state.status === "completed" ? "能力差距分析已完成。" :
        state.status === "cancelled" ? "你已拒绝这组目标岗位，本次分析已结束。" :
        state.status === "stale" ? careerAgentStepSummary(state.currentStep) :
        targetSelectionBlockMessage(state.currentStep) ?? "分析状态已更新。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "暂时无法提交；原请求已保留，请先查看状态或重试原请求。");
    } finally { commandLock.current = false; setBusy(false); }
  }

  async function showJobPage(offset: number) {
    if (pageLock.current) return;
    if (offset < jobs.length) { setVisibleOffset(offset); setJobPageError(null); return; }
    if (!hasMore) return;
    pageLock.current = true;
    setLoadingJobs(true); setJobPageError(null);
    try {
      const response = await workspaceFetch(`/api/jobs?offset=${pageOffset}`);
      if (!response.ok) throw new Error("暂时无法读取更多岗位，请稍后重试。");
      const page = await response.json();
      const next = appendAgentJobPage(jobs, page, pageOffset);
      setJobs(next.jobs); setPageOffset(next.offset); setHasMore(next.hasMore);
      if (next.jobs.length > offset) setVisibleOffset(offset);
      else setJobPageError("岗位列表刚刚有变化，已保留当前页和此前选中的岗位。");
    } catch (error) { setJobPageError(error instanceof Error ? error.message : "暂时无法读取更多岗位，请稍后重试。"); }
    finally { pageLock.current = false; setLoadingJobs(false); }
  }

  async function checkRanking() {
    if (!selected.length || checkLock.current) return;
    checkLock.current = true;
    const ids = [...selected];
    const scope = rankingScope(ids);
    setChecking(true); setPreflight(null); setPreflightError(null);
    try {
      const params = new URLSearchParams();
      ids.forEach(id => params.append("jobId", id));
      const response = await workspaceFetch(`/api/match-ranking/preflight?${params}`, {cache: "no-store"});
      if (!response.ok) throw new Error("暂时无法检查排序，请确认服务可用后重试。");
      setPreflight(rankingPreflight(ids, await response.json()));
    } catch (error) {
      setPreflightError({scope, message: error instanceof Error ? error.message : "暂时无法检查排序，请重试。"});
    } finally { checkLock.current = false; setChecking(false); }
  }

  async function startRun() {
    if (!currentPreflight?.candidates.length || checking || busy || pendingCommand) return;
    const threadId = newId("thread");
    await submitSavedCommand({version: 1, kind: "start", threadId, body: {
      threadId, runId: newId("run"), requestId: newId("request"),
      jobIds: [...selected], topN: Math.min(3, selected.length),
    }});
  }

  async function decide(decision: Decision) {
    if (!run?.interruptId || pendingCommand || busy) return;
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
      const state = await parseResponse(await workspaceFetch(
        `/api/career-agent/runs/${encodeURIComponent(run.threadId)}/continue`,
        {method: "POST"},
      ));
      displayState(state);
      setMessage(state.pendingApproval ? "分析已恢复，请确认目标岗位。" :
        state.status === "completed" ? "本次分析已完成。" :
        state.status === "stale" ? careerAgentStepSummary(state.currentStep) :
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
  const hasRankingResult = run && (run.pendingApproval || ["completed", "blocked", "cancelled"].includes(run.status));
  const unrankedJobIds = hasRankingResult
    ? run.requestedJobIds.filter(id => !run.rankedJobIds.includes(id)) : [];
  const jobLabels = {...runLabels, ...Object.fromEntries(jobs.map(job => [job.id, job.title]))};
  const activeJobIds = run?.requestedJobIds ?? selected;
  const activeJobNames = activeJobIds.map((id) => jobLabels[id] ?? "岗位名称暂不可读取");
  const requestSummary = activeJobNames.length > 0
    ? `帮我先比较这 ${activeJobNames.length} 个岗位，找出最值得优先考虑的岗位，再分析共同能力差距。`
    : "帮我比较目标岗位并分析共同能力差距。";
  const planSummary = run?.pendingApproval
    ? unrankedJobIds.length ? "仅部分所选岗位进入排序；请先查看未参与岗位，再决定是否确认目标。" : "已完成岗位排序；下一步需要你确认目标岗位，然后才会分析共同能力差距。"
    : run?.status === "completed"
      ? run.updatePartial || unrankedJobIds.length ? "已保存部分范围的目标分析；未参与排序的岗位不代表已淘汰。" : "岗位排序 → 人工确认 → 能力差距分析已完成。"
      : run?.currentStep === "update_matching"
        ? "已按固定事实处理当前小批；请查看逐岗位结果，明确继续下一批或仅使用已完成岗位。"
      : run
        ? careerAgentStepSummary(run.currentStep)
        : "选择岗位后，系统会先读取已有匹配结果并排序；目标岗位必须由你确认后才继续能力差距分析。";

  return (
    <div className="stack-lg">
      {(run || pendingCommand || recoverableThreadId) && <Panel className="stack-sm" aria-label="本次比较详情">
        <h2>比较进度与下一步</h2>
        {hasRankingResult && <p className="jl-scope-count">已选 {run.requestedJobIds.length} 个岗位，实际比较 {run.rankedJobIds.length} 个。</p>}
        {!busy && <p>{planSummary}</p>}
        <ActionFeedback>{message}</ActionFeedback>
        <details>
          <summary>查看本次范围与依据</summary>
          <p>{requestSummary} 只使用已保存的报告、已核对的岗位要求和你确认的经历。</p>
          {activeJobNames.length > 0 && <p>当前岗位范围：{activeJobNames.join("、")}</p>}
          {run?.updateSourceThreadId && <p>这次更新不会覆盖旧结果。<Link href={`/agent/results/${encodeURIComponent(run.updateSourceThreadId)}`}>查看原分析</Link></p>}
          {run?.gapResultFingerprint && <p className="muted">能力差距结果指纹：{run.gapResultFingerprint}</p>}
        </details>
      </Panel>}
      {!!run?.updateSteps?.length && <UpdateMatchProgress key={run.threadId} run={run} jobTitles={jobLabels} onState={state => {
        displayState(state);
        setMessage(state.pendingApproval ? "岗位排序已完成，请确认目标岗位。" : targetSelectionBlockMessage(state.currentStep) ?? "本次处理已保存，请查看当前状态。");
      }} />}
      {pendingCommand && !busy && (
        <section className="card stack-md" aria-label="未确认请求">
          <h2>这次请求的结果尚未确认</h2>
          <p>原岗位范围和决定已保存。请先查看服务端状态；需要重试时会沿用原标识和原内容，不会改成另一决定。</p>
          <p className="muted">{pendingCommand.kind === "start"
            ? `原请求：分析 ${pendingCommand.body.jobIds.map((id) => jobLabels[id] ?? "岗位名称暂不可读取").join("、")}；最多建议 ${pendingCommand.body.topN} 个目标。`
            : `原决定：${pendingCommand.body.decision === "approve" ? "确认建议" : pendingCommand.body.decision === "reject" ? "拒绝并结束" : `确认所选 ${pendingCommand.body.selectedJobIds.length} 个目标`}。`}</p>
          <div className="button-row">
            <button className="button primary" disabled={busy} onClick={() => void recoverRun(pendingCommand.threadId)} type="button">查看请求状态</button>
            <button className="button" disabled={busy} onClick={() => void submitSavedCommand(pendingCommand)} type="button">重试原请求</button>
          </div>
        </section>
      )}

      {!run && recoverableThreadId && !pendingCommand && !busy && (
        <section className="card stack-md">
          <div>
            <p className="eyebrow">继续上次比较</p>
            <h2>上次比较仍可继续</h2>
            <p className="muted">刚才可能只是网络或服务暂时不可用。JobLens 已保留上次比较记录，不会因为一次读取失败就重新排序。</p>
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
                setMessage("已放弃本地上次比较的本地记录，可以开始新的比较。");
              }}
              type="button"
            >
              结束上次比较
            </button>
          </div>
        </section>
      )}

      {!run && !recoverableThreadId && jobs.length > 0 && (
        <Panel className="stack-md">
          <div>
            <h2>选择要一起分析的岗位</h2>
            <p className="muted">{initialScope !== undefined || initialJobId !== undefined
              ? "已带回你刚才指定的岗位；可以更改勾选，或先检查本批有哪些岗位需要补充。"
              : "请勾选你想比较的岗位；不会替你选入无关或待补充的岗位。"}一次最多比较 50 个岗位，只读取已有匹配报告，不会调用模型。</p>
          </div>
          <div className="jl-inline">
            <Button variant="secondary" disabled={checking || busy || loadingJobs || pageJobs.every(job => selected.includes(job.id)) || selected.length >= 50}
              onClick={() => {
                setPreflight(null); setPreflightError(null);
                setSelected(current => Array.from(new Set([...current, ...pageJobs.map(job => job.id)])).slice(0, 50));
              }}>本页全选（最多共选 50 个）</Button>
            {selected.length > 0 && <Button variant="subtle" disabled={checking || busy} onClick={() => {
              setSelected([]); setPreflight(null); setPreflightError(null);
            }}>清除全部已选</Button>}
          </div>
          <div className="stack-sm">
            {pageJobs.map((job) => (
              <label className="check-row" key={job.id}>
                <input
                  type="checkbox"
                  checked={selected.includes(job.id)}
                  disabled={checking || busy || (!selected.includes(job.id) && selected.length >= 50)}
                  onChange={(event) => {
                    const checked = event.target.checked;
                    setPreflight(null);
                    setPreflightError(null);
                    setSelected(current => checked
                      ? Array.from(new Set([...current, job.id])).slice(0, 50)
                      : current.filter(id => id !== job.id));
                  }}
                />
                <span><strong>{job.title}</strong> · {job.company}</span>
              </label>
            ))}
          </div>
          <Pagination label="可比较岗位分页" count={pageJobs.length} offset={visibleOffset} limit={PAGE_SIZE}
            hasMore={visibleOffset + PAGE_SIZE < jobs.length || hasMore} onChange={offset => void showJobPage(offset)} />
          {loadingJobs && <PendingIndicator label="正在读取下一页；已选岗位不会丢失。" />}
          {jobPageError && <ActionFeedback tone="danger">{jobPageError}</ActionFeedback>}
          <p className="muted" role="status">跨页已选 {selected.length} / 50 个岗位 · 本页已选 {pageJobs.filter(job => selected.includes(job.id)).length} 个。</p>
          <div className="jl-inline"><Button variant={currentPreflight ? "secondary" : "primary"} aria-busy={checking} disabled={busy || checking || selected.length === 0}
            onClick={() => void checkRanking()} type="button">{checking ? "正在检查…" : currentPreflight ? "重新检查所选岗位" : "检查所选岗位"}</Button></div>
          {preflightError?.scope === currentScope && <ActionFeedback tone="danger">{preflightError.message}</ActionFeedback>}
          {currentPreflight && <div className="stack-sm" aria-live="polite">
            <p className="jl-scope-count">已选 {selected.length} 个岗位，目前有 {currentPreflight.ranked.length} 个可以比较。</p>
            <p className="muted">正式分析时会重新核对；可以比较不等于会推荐。</p>
            {currentPreflight.omissions.length > 0 && <aside className="notice ranking-omissions" aria-label="未进入排序的岗位及原因">
              <strong>{currentPreflight.omissions.length} 个岗位暂未进入默认排序</strong>
              <p>未进入排序不等于你不具备相关能力。以下原因仅基于当前保存的记录，正式分析时会重新检查。</p>
              <ul>{currentPreflight.omissions.map(item => <li key={item.jobId}>
                <Link href={`${jobDetailWithAgentScope(item.jobId, selected)}#${rankingRecoveryAnchor(item)}`}>{jobLabels[item.jobId] ?? "岗位名称暂不可读取"}<LinkFeedback /></Link>：{rankingOmissionMessage(item)}
              </li>)}</ul>
            </aside>}
            {currentPreflight.omissions.some(item => item.reason === "report_stale" || (item.reason === "report_missing" && !item.recoveryCode)) && <Callout tone="info" className="stack-sm">
              <p>缺少或过期的报告可以按当前已确认事实重新分析。先预览这批岗位需要哪些处理，再明确启动；旧报告保留，需要模型时不会自动调用。</p>
              <Button variant={currentPreflight.candidates.length ? "secondary" : "primary"} asChild><Link href={initialScopeAnalysisHref(selected)}>按当前事实分析这批岗位</Link></Button>
            </Callout>}
            {currentPreflight.insufficient.length > 0 && <aside className="notice" aria-label="暂不提出目标建议的岗位">
              <strong>{currentPreflight.insufficient.length} 个岗位可以查看，但当前证据不足以提出目标建议</strong>
              <p>这不代表你不具备相应能力。可以查看要求、核对已有事实，补充确认后的真实证据，再更新匹配报告。</p>
              <ul>{currentPreflight.insufficient.map(id => <li key={id}><Link href={jobDetailWithAgentScope(id, selected)}>{jobLabels[id] ?? "岗位名称暂不可读取"}：查看岗位和匹配依据</Link></li>)}</ul>
            </aside>}
            {currentPreflight.ranked.length > 0 && !currentPreflight.candidates.length && <p>当前没有足够依据提出目标建议，请先查看岗位及匹配依据，更新后重新检查。</p>}
          </div>}
          {!currentPreflight && selected.length > 0 && <p className="muted">请先检查当前所选岗位；更改选择后需重新检查。</p>}
          {!!currentPreflight?.candidates.length && <div className="jl-inline"><Button aria-busy={busy} disabled={busy || checking} onClick={startRun} type="button">
            {busy ? "正在比较…" : compareButtonLabel}
          </Button></div>}
        </Panel>
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
        <Panel className="stack-md">
          <div>
            <h2>确认要准备的岗位</h2>
            <p className="muted">默认建议最多 3 个；你可调整并确认最多 5 个。只有确认后才会继续能力差距分析，不能直接选择没有有效报告的岗位。</p>
            {run.targetSuggestionMode === "challenge_only" ? <p className="notice">本次只有挑战／待核实目标，没有优先投入建议。相关基础不代表条件已全部满足，请先查看关键未知。</p> : null}
            <p>请查看每个岗位本次排序所用的已保存匹配依据；报告可帮助你核对支持证据和待确认条件。</p>
            <UnrankedJobs ids={unrankedJobIds} labels={jobLabels} scope={run.requestedJobIds} currentOmissions={currentPreflight?.scope === rankingScope(run.requestedJobIds) ? currentPreflight.omissions : undefined} />
          </div>
          <div className="stack-sm">
            {run.rankedJobIds.map((jobId, index) => {
              const job = jobsById.get(jobId);
              return (
                <div className="stack-sm" key={jobId}><label className="check-row">
                  <input
                    type="checkbox"
                    checked={edited.includes(jobId)}
                    disabled={busy || !!pendingCommand || (!edited.includes(jobId) && edited.length >= 5)}
                    onChange={(event) => setEdited((current) => event.target.checked
                      ? Array.from(new Set([...current, jobId])).slice(0, 5)
                      : current.filter((id) => id !== jobId))}
                  />
                  <span><RankedJobLabel job={job} label={jobLabels[jobId]} jobId={jobId} />{!run.proposedTargetJobIds.includes(jobId) ? " · 非默认建议，请先核对证据与未知" : ""}</span>
                </label>
                {run.rankedReportRefs?.find(ref => ref.jobId === jobId)?.reportId ? <RankedJobExplanation jobId={jobId} reportId={run.rankedReportRefs.find(ref => ref.jobId === jobId)!.reportId} position={index + 1} /> : null}
                {run.rankedReportRefs?.find(ref => ref.jobId === jobId)?.reportId ? <Link href={rankedReportHref(jobId, run.rankedReportRefs.find(ref => ref.jobId === jobId)!.reportId, run.threadId)}>查看本次排序使用的匹配依据</Link> : <p className="muted">本次运行未保存可核对的报告引用，请查看岗位详情，不会将最新报告冒充当时依据。</p>}
                </div>
              );
            })}
          </div>
          <div className="jl-inline">
            {rankingScope(edited) === rankingScope(run.proposedTargetJobIds)
              ? <Button aria-busy={busy} disabled={busy || !!pendingCommand} onClick={() => decide("approve")}>{busy ? "正在确认目标…" : "确认这些目标并继续"}</Button>
              : <Button aria-busy={busy} disabled={busy || !!pendingCommand || edited.length === 0} onClick={() => decide("edit")}>{busy ? "正在确认目标…" : "按当前勾选继续"}</Button>}
            <Button variant="secondary" disabled={busy || !!pendingCommand} onClick={() => decide("reject")}>结束这次比较</Button>
          </div>
        </Panel>
      )}

      {run && !run.pendingApproval && !["created", "running", "resuming"].includes(run.status) && (
        <section className="card stack-md">
          <p className="eyebrow">比较状态 · {RUN_STATUS_LABELS[run.status] ?? "待核实"}</p>
          <h2>{run.status === "completed" ? run.updatePartial ? "已保存部分范围的能力差距分析" : "目标与准备材料已保存" : "本次比较已结束或暂停"}</h2>
          {run.status === "stale" && <div className="notice">
            <p>{careerAgentStepSummary(run.currentStep)}</p>
            <a href={workspacePath(run.requestedJobIds.length ? agentScopeHref(run.requestedJobIds) : "/agent")}>检查原岗位范围并重新分析</a>
          </div>}
          <UnrankedJobs ids={unrankedJobIds} labels={jobLabels} scope={run.requestedJobIds} currentOmissions={currentPreflight?.scope === rankingScope(run.requestedJobIds) ? currentPreflight.omissions : undefined} />
          {run.currentStep === "analysis_facts_changed" ? <p className="notice">分析期间资料、意向或岗位事实发生变化。本次材料如已保存，仅供历史查看；请使用当前事实新建分析。</p> : null}
          {run.legacyReadOnly ? <p className="notice">旧运行仅供历史查看。旧结果没有保存可重开的原始分析快照，未完成的旧运行也不会按新规则继续；请开始新分析。</p> : null}
          {run.status === "blocked" ? <div className="actions">
            <Link href="/recommendations">查看分类和逐项原因</Link>
            <Link href="/profile">核实职业资料与求职意向</Link>
          </div> : null}
          {run.confirmedTargetJobIds.length > 0 && <p className="muted">已确认目标岗位：{run.confirmedTargetJobIds.map((id) => jobLabels[id] ?? "岗位名称暂不可读取").join("、")}</p>}
          {run.gapResultFingerprint && !run.resultId && <p className="muted">已保存本次分析指纹，完整结果快照尚未保存（{run.gapResultFingerprint.slice(0, 12)}…）。</p>}
          {run.resultId ? <div className="actions">
            <Link className="button primary" href={`/agent/results/${encodeURIComponent(run.threadId)}`}>打开已保存的分析与准备材料<LinkFeedback /></Link>
            <p className="muted">查看本次事实版本下的原始结果，不会重新计算或调用模型。</p>
          </div> : null}
          {gapHandoffHref && !run.resultId && (
            <div className="actions">
              <Link className="button primary" href={gapHandoffHref}>按当前资料查看能力差距</Link>
              <p className="muted">使用已确认的目标岗位查看需要核对的条件、对应岗位和准备标准。</p>
            </div>
          )}
          <button className="button" type="button" onClick={() => {setRun(null); setPendingCommand(null); setPreflight(null); setPreflightError(null); window.history.replaceState(null, "", "/agent"); try { window.localStorage.removeItem(STORAGE_KEY); } catch {} setMessage("可以开始新的比较。");}}>开始新的比较</button>
        </section>
      )}

      <section className="card stack-md" aria-label="最近分析">
        <h2>最近分析</h2>
        <p className="muted">从服务端读取已保存的运行；打开只查看状态，不会自动继续分析。旧独立检查点文件不在此列表中。</p>
        {recentError ? <p role="alert">{recentError}</p> : null}
        <button className="button" disabled={busy} onClick={() => void loadRecentRuns()} type="button">刷新最近分析</button>
        {recentRuns.length === 0 && !recentError ? <p>暂无已保存分析。</p> : null}
        <ul>{recentRuns.map((item) => <li key={item.threadId}>
          <a href={workspacePath(runHref(item.threadId))}>{item.requestedJobIds.length} 个岗位 · {item.updatePartial ? "部分范围已保存" : RUN_STATUS_LABELS[item.status] ?? "已保存"}</a>
        </li>)}</ul>
      </section>

      {!run && !pendingCommand && !recoverableThreadId && <p className="muted" role="status">{message}</p>}
    </div>
  );
}

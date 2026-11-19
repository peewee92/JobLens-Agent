"use client";

import Link from "next/link";
import {Pagination} from "./ui/pagination";
import {PendingIndicator} from "./ui/pending-indicator";
import {lastPageOffset} from "@/lib/pagination";
import {Button} from "./ui/button";
import {ActionFeedback} from "./ui/patterns";
import {Badge, Callout, Field} from "./ui/primitives";
import {LinkFeedback} from "@/components/link-feedback";
import {useExistingMatchStatus} from "@/components/existing-match-status";
import {useRef, useState} from "react";
import type {ManualJobInput, ManualJobImportResult} from "@/lib/contracts";
import {jobDescriptionIssue} from "@/lib/job-requirements";
import {agentScopeHref, jobDetailWithAgentScope} from "@/lib/agent-job-scope";
import {duplicatePastedJobIndices, hasPastedJobDividers, isUnlistedPastedCompany, manualJobValidation, maxPastedCharacters, parsePastedJobs, submitManualJob} from "@/lib/manual-job-import";

import {savePastedJobScope} from "@/lib/pasted-job-session";

const rowLimit = 6;

type Row = {
  key: number;
  job: ManualJobInput;
  outcome?: {kind: "saved"; result: ManualJobImportResult} | {kind: "error" | "unknown"; message: string};
};

export function PastedJobsForm({onSaved}: {onSaved: (ids: string[]) => void}) {
  const [draft, setDraft] = useState("");
  const [dividersAreDescription, setDividersAreDescription] = useState(false);
  const [rows, setRows] = useState<Row[]>([]);
  const [requestedOffset, setOffset] = useState(0);
  const offset = Math.min(requestedOffset, lastPageOffset(rows.length, rowLimit));
  const firstInvalid = useRef<HTMLDivElement | null>(null);
  const [feedback, setFeedback] = useState("");
  const [working, setWorking] = useState<number | null>(null);
  const submitting = useRef(false);
  const hasReceipts = rows.some(row => !!row.outcome);
  const uncertain = rows.some(row => row.outcome?.kind === "unknown");
  const scope = [...new Set(rows.flatMap(row => row.outcome?.kind === "saved" ? [row.outcome.result.jobId] : []))];
  const pending = rows.filter(row => row.outcome?.kind !== "saved" && row.outcome?.kind !== "unknown");
  const duplicates = duplicatePastedJobIndices(rows.map(row => row.job));
  const validPending = pending.filter(row => !manualJobValidation(row.job));
  const invalidCount = pending.length - validPending.length;
  const companyUnlistedCount = pending.filter(row => isUnlistedPastedCompany(row.job.company)).length;
  const saved = rows.filter(row => row.outcome?.kind === "saved").length;
  const created = rows.filter(row => row.outcome?.kind === "saved" && row.outcome.result.created > 0).length;
  const failed = rows.filter(row => row.outcome?.kind === "error").length;
  const unknownCount = rows.filter(row => row.outcome?.kind === "unknown").length;
  const existingMatchStatus = useExistingMatchStatus(working === null ? rows.flatMap(row =>
    row.outcome?.kind === "saved" && !row.outcome.result.created ? [row.outcome.result.jobId] : []) : []);

  function preview() {
    try {
      const parsed = parsePastedJobs(draft, {dividersAreDescription});
      const badIndex = parsed.findIndex(job => manualJobValidation(job));
      setRows(parsed.map((job, key) => ({job, key})));
      setOffset(badIndex === -1 ? 0 : Math.floor(badIndex / rowLimit) * rowLimit);
      setFeedback("");
      if (badIndex !== -1) requestAnimationFrame(() => {
        const field = firstInvalid.current?.querySelector<HTMLElement>(`[data-row="${badIndex}"] [aria-invalid="true"]`);
        field?.focus();
      });
    } catch (error) {
      setFeedback(error instanceof Error ? error.message : "无法预览，未保存任何岗位。");
    }
  }

  function edit(index: number, field: keyof ManualJobInput, value: string) {
    setRows(previous => previous.map((row, i) => i === index ? {...row, outcome: undefined, job: {...row.job, [field]: value}} : row));
  }

  async function save(indices: number[]) {
    if (submitting.current) return;
    submitting.current = true;
    setFeedback("");
    const roundScope = new Set(scope);
    try {
      for (const index of indices) {
        setWorking(index);
        const outcome = await submitManualJob(rows[index].job);
        setRows(previous => previous.map((row, i) => i === index ? {...row, outcome} : row));
        if (outcome.kind === "saved") {
          roundScope.add(outcome.result.jobId);
          const ids = [...roundScope];
          try { savePastedJobScope(window.sessionStorage, ids); } catch { /* Storage is optional. */ }
          onSaved(ids);
        }
        if (outcome.kind === "unknown") {
          setOffset(Math.floor(index / rowLimit) * rowLimit);
          break;
        }
      }
    } finally {
      setWorking(null);
      submitting.current = false;
    }
  }

  return <section className="detail-card stack-md pasted-jobs-form" aria-label="批量粘贴岗位">
    <h2>一次粘贴多条岗位</h2>
    <Field id="pasted-job-text" label="岗位列表原文" hint="第一行写岗位名，或写「岗位名｜公司名」；下一行粘贴描述。用单独一行 --- 分隔岗位，每批最多 20 条。">
      <textarea id="pasted-job-text" aria-describedby="pasted-job-text-hint" rows={7} maxLength={maxPastedCharacters} value={draft} readOnly={working !== null || hasReceipts}
        onChange={event => {
          const text = event.target.value;
          setDraft(text); setRows([]); setFeedback("");
          if (dividersAreDescription && !hasPastedJobDividers(text)) setDividersAreDescription(false);
        }}
        placeholder={"岗位名称｜公司名称\n岗位描述原文\n\n---\n\n另一个岗位\n岗位描述原文"} />
    </Field>
    {hasPastedJobDividers(draft) && !hasReceipts && <label className="check-row">
      <input type="checkbox" checked={dividersAreDescription} disabled={working !== null}
        onChange={event => {setDividersAreDescription(event.target.checked); setRows([]); setFeedback("");}} />
      <span>保留正文里的 ---（改用「岗位名｜公司名」的标题分隔岗位）</span>
    </label>}
    <div className="jl-inline">
      <Button disabled={!draft.trim() || working !== null || hasReceipts} onClick={preview}>预览岗位清单</Button>
      {hasReceipts && !uncertain && <button className="button-secondary" type="button" disabled={working !== null} onClick={() => {
        setDraft(""); setRows([]); setOffset(0); setFeedback(""); setDividersAreDescription(false);
      }}>开始新一批</button>}
    </div>
    {feedback && <ActionFeedback tone="danger">{feedback}</ActionFeedback>}
    {rows.length > 0 && <section className="stack-md" ref={firstInvalid} aria-label="待保存岗位清单">
      <h3>核对清单 · {rows.length} 条记录{duplicates.size ? ` · 批内重复 ${duplicates.size} 条` : ""}</h3>
      <p>这里只保存招聘原文。短描述可以留作待补充，不会用于匹配；保存后还要核对提取出的岗位要求。</p>
      {hasReceipts && <div className="jl-callout" role="status">
        <strong>本批处理结果</strong>
        <p>新增 {created} 条 · 复用 {saved - created} 条 · 失败 {failed} 条 · 结果未确认 {unknownCount} 条 · 待提交 {rows.length - saved - failed - unknownCount} 条</p>
        {uncertain && <p>已确认的结果保留在清单里。剩余条目暂停，请先核对结果未确认的一条。</p>}
      </div>}
      {working !== null && <PendingIndicator label={`正在保存第 ${working + 1} 条岗位…`} slowLabel="还在等待本次回执；已保存的条目不会丢失，请不要重复提交。" />}
      {companyUnlistedCount > 0 && <p className="jl-callout" data-tone="warning" role="status">有 {companyUnlistedCount} 条没有公司名。知道的话，可在「查看或修改原文」里补上；不确定也可以先按「公司未公开」保存。</p>}
      {invalidCount > 0 && <div className="jl-callout" data-tone="warning" role="status">还有 {invalidCount} 条需要补充，可先保存内容完整的岗位。</div>}
      {offset !== requestedOffset && <p className="jl-callout" role="status">清单刚刚有变化，已显示最后一个有效页面。</p>}
      <ol className="paste-job-list" start={offset + 1}>
        {rows.slice(offset, offset + rowLimit).map((row, i) => {
          const index = i + offset;
          const result = row.outcome?.kind === "saved" ? row.outcome.result : null;
          const validation = manualJobValidation(row.job);
          const short = !validation && !!jobDescriptionIssue(row.job.description);
          const companyUnlisted = isUnlistedPastedCompany(row.job.company);
          const locked = working !== null || row.outcome?.kind === "unknown" || !!result;
          return <li key={row.key} className="paste-job-row" data-row={index}>
            <strong>{row.job.title || "未命名岗位"} · {row.job.company || "公司待填"}</strong>
            {(!result || companyUnlisted) && <div className="jl-inline">
              {!result && (duplicates.has(index) ? <Badge tone="info">批内重复</Badge> : <Badge>待保存</Badge>)}
              {companyUnlisted && <Badge tone="warning">公司名待核实</Badge>}
              {!result && short && <Badge tone="warning">描述待补充</Badge>}
            </div>}
            {!result && duplicates.has(index) && <Callout tone="info">与本批前面一条完全相同，实际新增以保存结果为准。</Callout>}
            {working === index ? <p className="muted">这条正在保存。</p>
            : result ? <div className="success-box" role="status">
              <p>{result.created ? "已添加" : "复用已有岗位，未新增"}{result.created && short ? " · 描述待补充，暂不能分析" : ""}</p>
              {!result.created && <p>{existingMatchStatus(result.jobId)}</p>}
              {working === null ? <Link href={`${jobDetailWithAgentScope(result.jobId, scope)}#${!result.created ? "job-match" : short ? "job-description" : "job-requirements"}`}>{!result.created ? "核对已有岗位和匹配" : short ? "查看并补充描述" : "查看这个岗位并分析要求"}<LinkFeedback /></Link> : <p>整批保存结束后可继续，返回时会保留这批岗位。</p>}
            </div> : short ? <p className="notice">描述信息不足。保存后标为待补充，不会直接参与匹配。</p> : null}
            {!result && <details open={validation ? true : undefined}>
              <summary>{locked ? "查看原文" : "查看或修改原文"}</summary>
              <label className="file-field">岗位名称<input value={row.job.title} maxLength={255} aria-invalid={!row.job.title.trim()} aria-describedby={validation ? `paste-row-error-${row.key}` : undefined} readOnly={locked} onChange={event => edit(index, "title", event.target.value)} /></label>
              <label className="file-field">公司名称<input value={row.job.company} maxLength={255} aria-invalid={!row.job.company.trim()} aria-describedby={validation ? `paste-row-error-${row.key}` : undefined} readOnly={locked} onChange={event => edit(index, "company", event.target.value)} /></label>
              <label className="file-field">岗位描述<textarea value={row.job.description} rows={5} aria-invalid={!row.job.description.trim()} aria-describedby={validation ? `paste-row-error-${row.key}` : undefined} readOnly={locked} onChange={event => edit(index, "description", event.target.value)} /></label>
            </details>}
            {validation && <p className="inline-error" id={`paste-row-error-${row.key}`}>{validation}</p>}
            {!locked && <button className="button-ghost" type="button" onClick={() => setRows(previous => previous.filter((_, i) => i !== index))}>从清单移除这条</button>}
            {row.outcome && row.outcome.kind !== "saved" && <p className="inline-error" role="alert">{row.outcome.message}</p>}
            {row.outcome?.kind === "unknown" && <div className="actions">
              <Link className="button-secondary" href="/jobs" target="_blank" rel="noopener">在新标签页核对我的岗位</Link>
              <button className="button-secondary" type="button" disabled={working !== null} onClick={() => void save([index])}>我已核对，重试这条</button>
            </div>}
          </li>;
        })}
      </ol>
      <Pagination label="预览清单分页" offset={offset} count={Math.min(rowLimit, rows.length - offset)} limit={rowLimit} total={rows.length} onChange={setOffset} />
      <div className="actions">
        {validPending.length > 0 && <Button disabled={working !== null || uncertain}
          onClick={() => void save(rows.flatMap((row, i) => validPending.includes(row) ? [i] : []))}>
          {working !== null ? "正在保存岗位…" : invalidCount ? `先保存 ${validPending.length} 条有效记录` : `保存 ${validPending.length} 条记录（重复不新增）`}
        </Button>}
        {working === null && scope.length > 0 && <Button asChild><Link href={agentScopeHref(scope)}>继续核对这批 {scope.length} 个岗位<LinkFeedback /></Link></Button>}
      </div>
    </section>}
  </section>;
}

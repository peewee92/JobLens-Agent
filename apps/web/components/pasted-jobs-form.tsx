"use client";

import Link from "next/link";
import {Button} from "./ui/button";
import {ActionFeedback} from "./ui/patterns";
import {Badge, Callout, Field} from "./ui/primitives";
import {LinkFeedback} from "@/components/link-feedback";
import {useExistingMatchStatus} from "@/components/existing-match-status";
import {useRef, useState} from "react";
import type {ManualJobInput, ManualJobImportResult} from "@/lib/contracts";
import {jobDescriptionIssue} from "@/lib/job-requirements";
import {agentScopeHref, jobDetailWithAgentScope} from "@/lib/agent-job-scope";
import {duplicatePastedJobIndices, hasPastedJobDividers, manualJobValidation, maxPastedCharacters, parsePastedJobs, submitManualJob} from "@/lib/manual-job-import";

import {savePastedJobScope} from "@/lib/pasted-job-session";

type Row = {
  key: number;
  job: ManualJobInput;
  outcome?: {kind: "saved"; result: ManualJobImportResult} | {kind: "error" | "unknown"; message: string};
};

export function PastedJobsForm({onSaved}: {onSaved: (ids: string[]) => void}) {
  const [draft, setDraft] = useState("");
  const [dividersAreDescription, setDividersAreDescription] = useState(false);
  const [rows, setRows] = useState<Row[]>([]);
  const [feedback, setFeedback] = useState("");
  const [working, setWorking] = useState<number | null>(null);
  const submitting = useRef(false);
  const hasReceipts = rows.some(row => !!row.outcome);
  const uncertain = rows.some(row => row.outcome?.kind === "unknown");
  const scope = [...new Set(rows.flatMap(row => row.outcome?.kind === "saved" ? [row.outcome.result.jobId] : []))];
  const pending = rows.filter(row => row.outcome?.kind !== "saved" && row.outcome?.kind !== "unknown");
  const duplicates = duplicatePastedJobIndices(rows.map(row => row.job));
  const hasInvalid = pending.some(row => manualJobValidation(row.job));
  const existingMatchStatus = useExistingMatchStatus(working === null ? rows.flatMap(row =>
    row.outcome?.kind === "saved" && !row.outcome.result.created ? [row.outcome.result.jobId] : []) : []);

  function preview() {
    try {
      setRows(parsePastedJobs(draft, {dividersAreDescription}).map((job, key) => ({job, key})));
      setFeedback("");
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
        if (outcome.kind === "unknown") break;
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
        setDraft(""); setRows([]); setFeedback(""); setDividersAreDescription(false);
      }}>开始新一批</button>}
    </div>
    {feedback && <ActionFeedback tone="danger">{feedback}</ActionFeedback>}
    {rows.length > 0 && <section className="stack-md" aria-label="待保存岗位清单">
      <h3>核对清单 · {rows.length} 条记录{duplicates.size ? ` · 批内重复 ${duplicates.size} 条` : ""}</h3>
      <p>这里只保存招聘原文。短描述可以留作待补充，不会用于匹配；保存后还要核对提取出的岗位要求。</p>
      <ol className="paste-job-list">
        {rows.map((row, index) => {
          const result = row.outcome?.kind === "saved" ? row.outcome.result : null;
          const validation = manualJobValidation(row.job);
          const short = !validation && !!jobDescriptionIssue(row.job.description);
          const locked = working !== null || row.outcome?.kind === "unknown" || !!result;
          return <li key={row.key} className="paste-job-row">
            <strong>{row.job.title || "未命名岗位"} · {row.job.company || "公司待填"}</strong>
            {!result && <div className="jl-inline">
              {duplicates.has(index) ? <Badge tone="info">批内重复</Badge> : <Badge>待保存</Badge>}
              {short && <Badge tone="warning">描述待补充</Badge>}
            </div>}
            {!result && duplicates.has(index) && <Callout tone="info">与本批前面一条完全相同，实际新增以保存结果为准。</Callout>}
            {working === index ? <p className="notice" role="status">正在保存这条岗位…</p>
            : result ? <div className="success-box" role="status">
              <p>{result.created ? "已添加" : "复用已有岗位，未新增"}{result.created && short ? " · 描述待补充，暂不能分析" : ""}</p>
              {!result.created && <p>{existingMatchStatus(result.jobId)}</p>}
              {working === null ? <Link href={`${jobDetailWithAgentScope(result.jobId, scope)}#${!result.created ? "job-match" : short ? "job-description" : "job-requirements"}`}>{!result.created ? "核对已有岗位和匹配" : short ? "查看并补充描述" : "查看这个岗位并分析要求"}<LinkFeedback /></Link> : <p>整批保存结束后可继续，返回时会保留这批岗位。</p>}
            </div> : short ? <p className="notice">描述信息不足。保存后标为待补充，不会直接参与匹配。</p> : null}
            {!result && <details open={validation ? true : undefined}>
              <summary>{locked ? "查看原文" : "查看或修改原文"}</summary>
              <label className="file-field">岗位名称<input value={row.job.title} maxLength={255} readOnly={locked} onChange={event => edit(index, "title", event.target.value)} /></label>
              <label className="file-field">公司名称<input value={row.job.company} maxLength={255} readOnly={locked} onChange={event => edit(index, "company", event.target.value)} /></label>
              <label className="file-field">岗位描述<textarea value={row.job.description} rows={5} readOnly={locked} onChange={event => edit(index, "description", event.target.value)} /></label>
            </details>}
            {validation && <p className="inline-error">{validation}</p>}
            {!locked && <button className="button-ghost" type="button" onClick={() => setRows(previous => previous.filter((_, i) => i !== index))}>从清单移除这条</button>}
            {row.outcome && row.outcome.kind !== "saved" && <p className="inline-error" role="alert">{row.outcome.message}</p>}
            {row.outcome?.kind === "unknown" && <div className="actions">
              <Link className="button-secondary" href="/jobs" target="_blank" rel="noopener">在新标签页核对我的岗位</Link>
              <button className="button-secondary" type="button" disabled={working !== null} onClick={() => void save([index])}>我已核对，重试这条</button>
            </div>}
          </li>;
        })}
      </ol>
      <div className="actions">
        {pending.length > 0 && <Button disabled={working !== null || uncertain || hasInvalid}
          onClick={() => void save(rows.flatMap((row, i) => row.outcome?.kind !== "saved" && row.outcome?.kind !== "unknown" ? [i] : []))}>
          {working !== null ? "正在保存岗位…" : `保存 ${pending.length} 条记录（重复不新增）`}
        </Button>}
        {working === null && scope.length > 0 && <Button asChild><Link href={agentScopeHref(scope)}>继续核对这批 {scope.length} 个岗位<LinkFeedback /></Link></Button>}
      </div>
    </section>}
  </section>;
}

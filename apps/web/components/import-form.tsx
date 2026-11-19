"use client";

import {workspaceFetch} from "@/lib/workspace-path";
import Link from "next/link";
import {useRef, useState, type FormEvent} from "react";
import type {ApiErrorBody, JobImportResult} from "@/lib/contracts";
import {userFacingApiError} from "@/lib/user-facing-errors";
import {Button} from "./ui/button";
import {FilePicker} from "./ui/file-picker";
import {PendingIndicator} from "./ui/pending-indicator";
import {ActionFeedback} from "./ui/patterns";

type ImportState =
  | {status: "idle" | "reading" | "submitting" | "unknown"}
  | {status: "success"; result: JobImportResult}
  | {status: "error"; message: string};

export function ImportForm() {
  const [file, setFile] = useState<File | null>(null);
  const [state, setState] = useState<ImportState>({status: "idle"});
  const inFlight = useRef(false);
  const busy = state.status === "reading" || state.status === "submitting";
  const unknown = state.status === "unknown";

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (inFlight.current || unknown || !file) return;
    inFlight.current = true;
    setState({status: "reading"});
    try {
      let payload: unknown;
      try { payload = JSON.parse(await file.text()); }
      catch { setState({status: "error", message: "文件不是有效 JSON，没有提交。请重新导出后再选择。"}); return; }
      if (typeof payload !== "object" || payload === null || Array.isArray(payload)) {
        setState({status: "error", message: "这不是 JobLens 岗位文件，没有提交。请从浏览器插件重新导出。"});
        return;
      }
      setState({status: "submitting"});
      const response = await workspaceFetch("/api/job-imports", {
        method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload),
      });
      if (response.status >= 500 || response.status === 408) { setState({status: "unknown"}); return; }
      const body = await response.json();
      if (!response.ok) {
        setState({status: "error", message: userFacingApiError(body as ApiErrorBody, "这批岗位没有通过检查，所选文件仍保留。请核对格式后再试。")});
        return;
      }
      const result = body as JobImportResult;
      if (!result.importId || !Array.isArray(result.errors)) { setState({status: "unknown"}); return; }
      setState({status: "success", result});
      setFile(null);
    } catch { setState({status: "unknown"}); }
    finally { inFlight.current = false; }
  }

  return <form className="import-card stack-md" onSubmit={submit}>
    <h2>添加浏览器插件收集的岗位</h2>
    <p>选择插件导出的 JSON 文件。系统会检查格式和重复项，单条出错不影响其他有效条目。</p>
    <FilePicker title="岗位数据文件（JSON）" hint="只选择从 JobLens 浏览器插件导出的文件"
      accept="application/json,.json" disabled={busy || unknown} invalid={state.status === "error"}
      file={file} onSelect={value => { setFile(value); setState({status: "idle"}); }} />
    <div><Button type="submit" disabled={busy || unknown || !file}>
      {state.status === "reading" ? "正在读取文件…" : state.status === "submitting" ? "正在导入…" : "添加这些岗位"}
    </Button></div>
    {busy && <PendingIndicator label={state.status === "reading" ? "正在检查文件。" : "正在保存并核对每条岗位。"} />}
    {state.status === "error" && <ActionFeedback tone="danger">{state.message}</ActionFeedback>}
    {unknown && <ActionFeedback tone="warning">
      <h3>暂未收到导入结果</h3>
      <p>无法确认岗位是否已保存。文件仍保留，请先查看岗位列表；没有回执编号时不能确认这批的完整结果。没有自动重新提交。</p>
      <div className="jl-inline">
        <Button asChild><Link href="/jobs" target="_blank" rel="noopener">在新标签查看岗位</Link></Button>
        <Button variant="secondary" onClick={() => setState({status: "idle"})}>已核对，返回提交前</Button>
      </div>
    </ActionFeedback>}
    {state.status === "success" && <section className="success-box stack-sm" aria-live="polite">
      <h3>{state.result.errors.length ? "部分岗位需要核对" : "已处理这批岗位"}</h3>
      <p>收到 {state.result.received} 条 · 新增 {state.result.created} 条 · 更新 {state.result.updated} 条 · 跳过 {state.result.skipped} 条</p>
      {state.result.errors.length > 0 && <p>有 {state.result.errors.length} 条错误记录。打开回执可以逐条查看。</p>}
      <div className="jl-inline"><Button asChild><Link href={`/imports/${encodeURIComponent(state.result.importId)}`}>查看处理回执</Link></Button>
        <Link className="jl-text-link" href="/jobs">查看我的岗位</Link></div>
    </section>}
  </form>;
}

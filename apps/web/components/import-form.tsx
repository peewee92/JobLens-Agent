"use client";

import Link from "next/link";
import {FormEvent, useState} from "react";

import type {ApiErrorBody, JobImportResult} from "@/lib/contracts";

type ImportState =
  | {status: "idle"}
  | {status: "reading"}
  | {status: "submitting"}
  | {status: "success"; result: JobImportResult}
  | {status: "error"; message: string};

function errorMessage(body: unknown, fallback: string): string {
  if (
    typeof body === "object" &&
    body !== null &&
    "error" in body &&
    typeof (body as Partial<ApiErrorBody>).error?.message === "string"
  ) {
    return (body as ApiErrorBody).error.message;
  }
  return fallback;
}

export function ImportForm() {
  const [state, setState] = useState<ImportState>({status: "idle"});

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const file = new FormData(form).get("report");
    if (!(file instanceof File) || file.size === 0) {
      setState({status: "error", message: "请选择一个 Collector report JSON 文件。"});
      return;
    }

    setState({status: "reading"});
    let payload: unknown;
    try {
      payload = JSON.parse(await file.text());
    } catch {
      setState({status: "error", message: "文件不是有效 JSON，请检查后重新选择。"});
      return;
    }

    if (typeof payload !== "object" || payload === null || Array.isArray(payload)) {
      setState({status: "error", message: "Collector report 顶层必须是 JSON Object。"});
      return;
    }

    setState({status: "submitting"});
    try {
      const response = await fetch("/api/job-imports", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload),
      });
      const body = (await response.json()) as unknown;
      if (!response.ok) {
        setState({
          status: "error",
          message: errorMessage(body, `导入失败（HTTP ${response.status}）。`),
        });
        return;
      }
      setState({status: "success", result: body as JobImportResult});
      form.reset();
    } catch {
      setState({
        status: "error",
        message: "无法连接 JobLens Web 服务，请确认 Next.js 与 Backend 都已启动。",
      });
    }
  }

  const busy = state.status === "reading" || state.status === "submitting";

  return (
    <form className="import-card" onSubmit={submit}>
      <h2>选择 Collector report</h2>
      <p className="lede">
        上传插件导出的完整 JSON。Backend 会逐条校验岗位；单条错误不会阻止其余合法岗位导入。
      </p>
      <label className="file-field">
        <span>Collector JSON 文件</span>
        <input name="report" type="file" accept="application/json,.json" disabled={busy} />
      </label>
      <button className="button" type="submit" disabled={busy}>
        {state.status === "reading"
          ? "正在读取文件…"
          : state.status === "submitting"
            ? "正在导入…"
            : "开始导入"}
      </button>

      {state.status === "error" ? (
        <div className="inline-error" role="alert">{state.message}</div>
      ) : null}

      {state.status === "success" ? (
        <section className="success-box" aria-live="polite">
          <h3>导入完成</h3>
          <div className="summary-grid">
            <div className="summary-card"><span>收到</span><strong>{state.result.received}</strong></div>
            <div className="summary-card"><span>新建</span><strong>{state.result.created}</strong></div>
            <div className="summary-card"><span>更新</span><strong>{state.result.updated}</strong></div>
            <div className="summary-card"><span>跳过</span><strong>{state.result.skipped}</strong></div>
          </div>
          {state.result.errors.length > 0 ? (
            <p>有 {state.result.errors.length} 条输入需要检查，详情页会显示公开错误信息。</p>
          ) : (
            <p>本批次没有输入级错误。</p>
          )}
          <div className="actions">
            <Link className="button-secondary" href={`/imports/${state.result.importId}`}>
              查看导入审计
            </Link>
            <Link className="button-ghost" href="/jobs">查看岗位池</Link>
          </div>
        </section>
      ) : null}
    </form>
  );
}

"use client";

import Link from "next/link";
import {FormEvent, useState} from "react";

import type {ApiErrorBody, JobImportResult} from "@/lib/contracts";
import {userFacingApiError} from "@/lib/user-facing-errors";

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
    return userFacingApiError(body as Partial<ApiErrorBody>, fallback);
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
      setState({status: "error", message: "请选择浏览器插件导出的岗位 JSON 文件。"});
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
      setState({status: "error", message: "这个文件格式不符合 JobLens 的岗位导入格式，请重新从浏览器插件导出。"});
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
        message: "暂时无法处理这个文件，请稍后重试。",
      });
    }
  }

  const busy = state.status === "reading" || state.status === "submitting";

  return (
    <form className="import-card" onSubmit={submit}>
      <h2>添加浏览器插件收集的岗位</h2>
      <p className="lede">
        选择 JobLens 浏览器插件导出的 JSON 文件。系统会自动去重和检查格式；个别岗位有问题时，其余正常岗位仍会继续添加。
      </p>
      <label className="file-field">
        <span>岗位数据文件（JSON）</span>
        <input name="report" type="file" accept="application/json,.json" disabled={busy} />
      </label>
      <button className="button" type="submit" disabled={busy}>
        {state.status === "reading"
          ? "正在读取文件…"
          : state.status === "submitting"
            ? "正在导入…"
            : "添加这些岗位"}
      </button>

      {state.status === "error" ? (
        <div className="inline-error" role="alert">{state.message}</div>
      ) : null}

      {state.status === "success" ? (
        <section className="success-box" aria-live="polite">
          <h3>岗位已添加</h3>
          <div className="summary-grid">
            <div className="summary-card"><span>文件中的岗位</span><strong>{state.result.received}</strong></div>
            <div className="summary-card"><span>新增</span><strong>{state.result.created}</strong></div>
            <div className="summary-card"><span>信息已更新</span><strong>{state.result.updated}</strong></div>
            <div className="summary-card"><span>未添加</span><strong>{state.result.skipped}</strong></div>
          </div>
          {state.result.errors.length > 0 ? (
            <p>有 {state.result.errors.length} 条岗位没有成功添加，可以在处理详情里查看原因。</p>
          ) : (
            <p>所有岗位都已正常处理。</p>
          )}
          <div className="actions">
            <Link className="button-secondary" href={`/imports/${state.result.importId}`}>
              查看处理详情
            </Link>
            <Link className="button-ghost" href="/jobs">查看我的岗位</Link>
          </div>
        </section>
      ) : null}
    </form>
  );
}

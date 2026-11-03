"use client";

import Link from "next/link";
import {type FormEvent, useState} from "react";
import type {ApiErrorBody, ManualJobImportResult, ManualJobInput} from "@/lib/contracts";
import {userFacingApiError} from "@/lib/user-facing-errors";

export function ManualJobForm() {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [uncertain, setUncertain] = useState(false);
  const [result, setResult] = useState<ManualJobImportResult | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || uncertain || result) return;
    const data = new FormData(event.currentTarget);
    setBusy(true);
    setMessage("");
    const payload: ManualJobInput = {
      title: String(data.get("title") ?? ""), company: String(data.get("company") ?? ""),
      description: String(data.get("description") ?? ""), sourceUrl: String(data.get("sourceUrl") ?? "") || null,
    };
    try {
      const response = await fetch("/api/job-imports/manual", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload),
      });
      if (response.status >= 500 || response.status === 408) {
        setUncertain(true);
        setMessage("暂时无法确认岗位是否已保存。请先查看我的岗位，核对后再添加，不要连续重复提交。");
        return;
      }
      const body = await response.json();
      if (!response.ok) {
        setMessage(userFacingApiError(body as Partial<ApiErrorBody>, "没有保存成功，请检查必填内容和岗位链接。"));
        return;
      }
      setResult(body as ManualJobImportResult);
    } catch {
      setUncertain(true);
      setMessage("连接中断，暂时无法确认是否已保存。请先查看我的岗位；这里保留了你填写的内容。");
    } finally {
      setBusy(false);
    }
  }

  return <form className="import-card" onSubmit={submit}>
    <h2>粘贴一个目标岗位</h2>
    <p>复制真实岗位的完整描述即可，不需要先安装浏览器插件。这里仅保存岗位，不调用模型，也不会自动投递。</p>
    <label className="file-field"><span>岗位名称</span><input name="title" required maxLength={255} disabled={busy || !!result} /></label>
    <label className="file-field"><span>公司名称</span><input name="company" required maxLength={255} disabled={busy || !!result} /></label>
    <label className="file-field"><span>完整岗位描述</span><textarea name="description" required maxLength={50000} rows={12} disabled={busy || !!result} /></label>
    <label className="file-field"><span>原始岗位链接（可选）</span><input name="sourceUrl" type="url" maxLength={2048} placeholder="https://…" disabled={busy || !!result} /></label>
    <p className="muted-copy">系统会注明“手动粘贴”，不会把保存时间当成岗位仍在招聘的证明。未提供链接时，相同内容可复用；内容不同会作为另一个岗位保存。</p>
    <button className="button" disabled={busy || uncertain || !!result} type="submit">{busy ? "正在保存岗位…" : result ? "岗位已保存" : "保存岗位，继续分析"}</button>
    {message ? <div className="inline-error" role="alert">{message}</div> : null}
    {uncertain ? <Link className="button-secondary" href="/jobs">先核对我的岗位</Link> : null}
    {result ? <section className="success-box" aria-live="polite">
      <h3>{result.created ? "岗位已保存" : "已有岗位已更新"}</h3>
      <p>下一步检查岗位描述并分析要求。保存岗位不代表已经生成个人匹配结论；分析前仍需确认职业资料和求职意向。</p>
      <Link className="button" href={`/jobs/${encodeURIComponent(result.jobId)}`}>查看岗位并继续分析</Link>
    </section> : null}
  </form>;
}

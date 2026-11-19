"use client";

import Link from "next/link";
import {PendingIndicator} from "@/components/ui/pending-indicator";
import {LinkFeedback} from "@/components/link-feedback";
import {useExistingMatchStatus} from "@/components/existing-match-status";
import {type FormEvent, useRef, useState, useSyncExternalStore} from "react";
import type {ManualJobImportResult, ManualJobInput} from "@/lib/contracts";
import {submitManualJob} from "@/lib/manual-job-import";
import {jobDescriptionIssue} from "@/lib/job-requirements";

// Keep the native form from submitting until React can intercept it.
const subscribeToHydration = () => () => {};
const clientReady = () => true;
const serverReady = () => false;

export function ManualJobForm() {
  const ready = useSyncExternalStore(subscribeToHydration, clientReady, serverReady);
  const form = useRef<HTMLFormElement>(null);
  const sending = useRef(false);
  const [pendingDescription, setPendingDescription] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [uncertain, setUncertain] = useState(false);
  const [result, setResult] = useState<ManualJobImportResult | null>(null);
  const existingMatchStatus = useExistingMatchStatus(result && !result.created ? [result.jobId] : []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!ready || sending.current || uncertain || result) return;
    const data = new FormData(event.currentTarget);
    sending.current = true;
    setBusy(true);
    setMessage("");
    const payload: ManualJobInput = {
      title: String(data.get("title") ?? ""), company: String(data.get("company") ?? ""),
      description: String(data.get("description") ?? ""), sourceUrl: String(data.get("sourceUrl") ?? "") || null,
    };
    try {
      const outcome = await submitManualJob(payload);
      if (outcome.kind === "saved") {
        setPendingDescription(!!outcome.result.created && !!jobDescriptionIssue(payload.description));
        setResult(outcome.result);
      } else {
        setUncertain(outcome.kind === "unknown");
        setMessage(outcome.message);
      }
    } finally {
      sending.current = false;
      setBusy(false);
    }
  }

  return <form className="import-card manual-job-form" ref={form} method="post" onSubmit={submit}>
    <h2>粘贴一个目标岗位</h2>
    <p>复制真实岗位的完整描述即可，不需要先安装浏览器插件。这里仅保存岗位，不调用模型，也不会自动投递。</p>
    <label className="file-field"><span>岗位名称</span><input name="title" required maxLength={255} disabled={busy || !!result} /></label>
    <label className="file-field"><span>公司名称</span><input name="company" required maxLength={255} disabled={busy || !!result} /></label>
    <label className="file-field"><span>完整岗位描述</span><textarea name="description" required maxLength={50000} rows={8} disabled={busy || !!result} /></label>
    <label className="file-field"><span>原始岗位链接（可选）</span><input name="sourceUrl" type="url" maxLength={2048} placeholder="https://…" disabled={busy || !!result} /></label>
    <p className="muted-copy">系统会注明“手动粘贴”，不会把保存时间当成岗位仍在招聘的证明。未提供链接时，相同内容可复用；内容不同会作为另一个岗位保存。</p>
    <button className="button" disabled={!ready || busy || uncertain || !!result} type="submit">{!ready ? "正在准备表单…" : busy ? "正在保存岗位…" : result ? "岗位已保存" : "保存岗位，继续分析"}</button>
    {busy && <PendingIndicator label="正在保存岗位原文…" slowLabel="还没收到回执，页面会继续等待。请不要重复提交。" />}
    {message ? <div className="inline-error" role="alert">{message}</div> : null}
    {uncertain ? <Link className="button-secondary" href="/jobs" target="_blank" rel="noopener">在新标签核对我的岗位</Link> : null}
    {result ? <section className="success-box" aria-live="polite">
      <h3>{result.created ? "岗位已保存" : "复用已有岗位，未新增"}</h3>
      <p>{pendingDescription ? "描述信息不足，已保存为待补充，暂不能生成匹配。"
        : result.created ? "下一步核对原文和岗位要求，再生成匹配。"
        : existingMatchStatus(result.jobId)} </p>
      <div className="actions">
        <Link className="button" href={`/jobs/${encodeURIComponent(result.jobId)}#${pendingDescription ? "job-description" : result.created ? "job-requirements" : "job-match"}`}>{pendingDescription ? "查看并补充描述" : result.created ? "查看岗位并继续分析" : "核对已有岗位和匹配"}<LinkFeedback /></Link>
        <button className="button-secondary" type="button" onClick={() => {
          form.current?.reset();
          setResult(null);
          setPendingDescription(false);
          requestAnimationFrame(() => form.current?.querySelector<HTMLInputElement>("input[name=title]")?.focus());
        }}>再添加一条</button>
      </div>
    </section> : null}
  </form>;
}

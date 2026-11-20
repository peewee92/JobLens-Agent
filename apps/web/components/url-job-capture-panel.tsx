"use client";

import {type FormEvent, useEffect, useRef, useState, useSyncExternalStore} from "react";
import {captureGrades, captureJobUrl, captureMethods, type CapturedJobDraft, type CaptureDraftApplication, type CaptureOutcome} from "@/lib/url-job-capture";
import {Button} from "./ui/button";

const subscribe = () => () => {};
const ready = () => true;
const notReady = () => false;

export function UrlJobCapturePanel({onDraft, onPaste}: {
  onDraft: (draft: CapturedJobDraft, overwrite: boolean) => CaptureDraftApplication;
  onPaste: () => void;
}) {
  const hydrated = useSyncExternalStore(subscribe, ready, notReady);
  const pending = useRef<AbortController | null>(null);
  const [busy, setBusy] = useState(false);
  const [url, setUrl] = useState("");
  const [result, setResult] = useState<CaptureOutcome | null>(null);
  const [application, setApplication] = useState<CaptureDraftApplication | null>(null);
  useEffect(() => () => pending.current?.abort(), []);

  async function preview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!hydrated || pending.current) return;
    const controller = new AbortController();
    pending.current = controller;
    setBusy(true);
    setResult(null);
    setApplication(null);
    try {
      const next = await captureJobUrl(url.trim(), controller.signal);
      if (!controller.signal.aborted) {
        setResult(next);
        if (next.kind === "captured") setApplication(onDraft(next.draft, false));
      }
    } finally {
      pending.current = null;
      if (!controller.signal.aborted) setBusy(false);
    }
  }

  return <section className="import-card" aria-labelledby="url-capture-title">
    <h2 id="url-capture-title">从岗位链接抓取草稿</h2>
    <p>仅支持公开岗位页。预览不保存岗位，请核对后再手动保存。</p>
    <form onSubmit={preview}>
      <label className="file-field">
        <span>公开岗位链接</span>
        <input type="url" placeholder="https://…" required maxLength={2048} value={url}
          onChange={event => setUrl(event.target.value)} disabled={busy} />
      </label>
      <Button type="submit" variant="secondary" disabled={!hydrated || busy}>{busy ? "正在抓取…" : "抓取预览"}</Button>
    </form>
    {busy && <p role="status">正在读取岗位页面，请稍候。</p>}
    {result?.kind === "captured" && <div aria-live="polite">
      <p>描述质量：{captureGrades[result.details.qualityGrade]} · {captureMethods[result.details.extractionMethod]} · {(result.details.diagnostics.elapsedMs / 1000).toFixed(1)} 秒</p>
      {application === "applied" && <p>已将抓取结果填入下方表单。</p>}
      {application === "needs_confirmation" && <p>单条表单已有内容。只有确认替换才会改动。</p>}
      {application === "locked" && <p>当前岗位正在保存或已保存。请先处理当前岗位，再应用预览。</p>}
      {application !== "applied" && <Button type="button" variant="secondary"
        onClick={() => setApplication(onDraft(result.draft, application === "needs_confirmation"))}>
        {application === "needs_confirmation" ? "替换未保存草稿" : "应用抓取草稿"}
      </Button>}
    </div>}
    {result?.kind === "error" && <div>
      <p className="inline-error" role="alert">{result.message}</p>
      <Button type="button" variant="secondary" onClick={onPaste}>改用手动粘贴</Button>
    </div>}
  </section>;
}

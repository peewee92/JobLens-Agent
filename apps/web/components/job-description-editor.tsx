"use client";

import {type FormEvent, useRef, useState} from "react";
import {useRouter} from "next/navigation";
import {jobDescriptionIssue} from "@/lib/job-requirements";

export function JobDescriptionEditor({jobId, description, revision}: {
  jobId: string; description: string; revision: string;
}) {
  const router = useRouter();
  const lock = useRef(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [unverifiedRevision, setUnverifiedRevision] = useState("");
  const [savedRevision, setSavedRevision] = useState("");
  const [message, setMessage] = useState<{error: boolean; text: string}>();
  const currentDraft = draft ?? description;
  const issue = jobDescriptionIssue(currentDraft);
  const waitingOnSavedView = savedRevision === revision;
  const mustCheck = unverifiedRevision === revision || waitingOnSavedView;

  async function verify() {
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    try {
      const response = await fetch(`/api/jobs/${encodeURIComponent(jobId)}/manual-description`, {cache: "no-store"});
      if (!response.ok) throw new Error();
      const value = await response.json();
      if (!/^[0-9a-f]{64}$/.test(value?.revision)) throw new Error();
      if (value.revision === revision) {
        setUnverifiedRevision("");
        setSavedRevision("");
        setMessage({error: false, text: "已核对，系统中的原文未变化。可以继续修改或保存。"});
      } else {
        setMessage({error: false, text: "已读到更新后的版本。请先核对最新原文和你的草稿。"});
        router.refresh();
      }
    } catch {
      setMessage({error: true, text: "暂时读不到当前岗位原文。请检查连接后再刷新核对；页面没有重复提交。"});
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (lock.current || mustCheck || issue || description === currentDraft) return;
    lock.current = true;
    setBusy(true);
    setMessage(undefined);
    const uncertain = () => {
      setUnverifiedRevision(revision);
      setMessage({error: true, text: "还不能确认是否保存成功。请刷新核对上方原文；核对前不要重复提交。"});
    };
    try {
      const response = await fetch(`/api/jobs/${encodeURIComponent(jobId)}/manual-description`, {
        method: "PUT", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({description: currentDraft, expectedSha256: revision}),
      });
      const value = await response.json();
      if (response.ok && value?.jobId === jobId && /^[0-9a-f]{64}$/.test(value.descriptionSha256) && typeof value.changed === "boolean") {
        setEditing(false);
        setDraft(null);
        if (value.changed) setSavedRevision(revision);
        setMessage({error: false, text: value.changed
          ? "已补充描述，仍是同一个岗位。旧结果保留供查看；请用新描述重新分析并核对要求。"
          : "当前原文已是这份描述，无需重复保存。"});
        router.refresh();
      } else if (response.status === 422) {
        setMessage({error: true, text: "请贴入完整的岗位原文，包含职责与任职要求（40 到 50,000 字符）。"});
      } else if (value?.error?.code === "manual_description_identity_conflict") {
        setMessage({error: true, text: "同一份描述已属于另一个岗位。这里没有合并或修改岗位；请检查是否应使用已有岗位。"});
      } else if (value?.error?.code === "manual_description_source_read_only") {
        setMessage({error: true, text: "这个岗位有不可修改的采集来源，请回到原来源补全。"});
      } else if (value?.error?.code === "manual_description_changed") {
        setUnverifiedRevision(revision);
        setMessage({error: true, text: "岗位原文已经变化。本次没有覆盖；刷新核对新原文后再决定是否保存草稿。"});
      } else if (response.status === 404) {
        setMessage({error: true, text: "找不到这个岗位，没有写入描述。请返回岗位列表核对。"});
      } else {
        uncertain();
      }
    } catch {
      uncertain();
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }

  return <div className="job-description-editor">
    {jobDescriptionIssue(description) && <p className="notice">描述还不够完整。补上原文里的岗位职责和任职要求，才能继续分析；不要为了通过检查而编写要求。</p>}
    {!editing ? <button type="button" className="button-secondary" disabled={mustCheck} onClick={() => {setMessage(undefined); setEditing(true);}}>补充或更正岗位描述</button> :
      <form className="vertical-form" onSubmit={save}>
        <label htmlFor="updated-job-description">更新后的完整岗位原文</label>
        <textarea id="updated-job-description" rows={8} autoFocus value={currentDraft} readOnly={busy}
          onChange={event => setDraft(event.target.value)} aria-describedby="job-description-edit-hint" />
        <p className="muted-copy" id="job-description-edit-hint">{issue ? "请贴入至少 40 字符的完整岗位原文（最多 50,000 字符），包含实际职责与任职要求。" : "保存会保留旧原文。基于旧描述的记录仍能查看，但需要重新分析才能用于当前比较。"}</p>
        <div className="actions">
          <button type="submit" className="button" disabled={busy || mustCheck || !!issue || currentDraft === description}>
            {busy ? "正在保存描述…" : "保存描述"}
          </button>
          <button type="button" className="button-ghost" disabled={busy} onClick={() => {setEditing(false); setDraft(null);}}>取消</button>
        </div>
      </form>}
    {waitingOnSavedView && <p className="notice" role="status">已保存，正在读取更新后的原文…</p>}
    {!waitingOnSavedView && message && <p className={message.error ? "inline-error" : "success-box"} role={message.error ? "alert" : "status"}>{message.text}</p>}
    {mustCheck && <button type="button" className="button-ghost" disabled={busy} onClick={verify}>{busy ? "正在核对…" : waitingOnSavedView ? "重新读取原文" : "刷新核对原文"}</button>}
    {!editing && !mustCheck && message && !message.error && <a className="button-secondary" href="#job-requirements">继续分析岗位要求</a>}
  </div>;
}

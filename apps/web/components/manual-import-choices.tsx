"use client";

import Link from "next/link";
import {agentScopeHref} from "@/lib/agent-job-scope";
import {lastPastedJobScope} from "@/lib/pasted-job-session";
import {useEffect, useState} from "react";
import {ManualJobForm} from "./manual-job-form";
import {PastedJobsForm} from "./pasted-jobs-form";

export function ManualImportChoices() {
  const [batch, setBatch] = useState(false);
  const [previous, setPrevious] = useState<string[]>([]);
  useEffect(() => {
    try { setPrevious(lastPastedJobScope(window.sessionStorage)); } catch { /* Storage is optional. */ }
  }, []);
  return <>
    {!batch && previous.length > 0 && <p className="notice">
      <Link href={agentScopeHref(previous)}>继续比较上次保存的 {previous.length} 个岗位</Link>。只恢复已保存的岗位，不保留离开页面前未保存的文字。
    </p>}
    <div className="button-row" aria-label="手动添加方式">
      <button className="button-secondary" type="button" aria-pressed={!batch} onClick={() => setBatch(false)}>逐条填写</button>
      <button className="button-secondary" type="button" aria-pressed={batch} onClick={() => setBatch(true)}>批量粘贴文本</button>
    </div>
    <div hidden={batch}><ManualJobForm /></div>
    <div hidden={!batch}><PastedJobsForm onSaved={setPrevious} /></div>
  </>;
}

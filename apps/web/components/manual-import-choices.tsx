"use client";

import Link from "next/link";
import {agentScopeHref} from "@/lib/agent-job-scope";
import {lastPastedJobScope} from "@/lib/pasted-job-session";
import {useEffect, useState} from "react";
import {Button} from "./ui/button";
import {Callout} from "./ui/primitives";
import {ManualJobForm} from "./manual-job-form";
import {PastedJobsForm} from "./pasted-jobs-form";

export function ManualImportChoices() {
  const [batch, setBatch] = useState(true);
  const [previous, setPrevious] = useState<string[]>([]);
  useEffect(() => {
    try { setPrevious(lastPastedJobScope(window.sessionStorage)); } catch { /* Storage is optional. */ }
  }, []);
  return <>
    {previous.length > 0 && <Callout tone="info">
      <Link className="jl-text-link" href={agentScopeHref(previous)}>继续比较上次保存的 {previous.length} 个岗位</Link>。只恢复已保存的岗位，不保留离开页面前未保存的文字。
    </Callout>}
    <div className="jl-inline jl-import-options" aria-label="手动添加方式">
      <Button variant="secondary" aria-pressed={batch} onClick={() => setBatch(true)}>粘贴招聘描述</Button>
      <Button variant="secondary" aria-pressed={!batch} onClick={() => setBatch(false)}>逐条填写</Button>
    </div>
    <div hidden={batch}><ManualJobForm /></div>
    <div hidden={!batch}><PastedJobsForm onSaved={setPrevious} /></div>
  </>;
}

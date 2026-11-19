"use client";

import {OpenCatalogJob} from "./job-catalog-navigation";
import {useEffect, useState} from "react";
import {DetailDrawer} from "./ui/drawer";
import {Button} from "./ui/button";
import {PendingIndicator} from "./ui/pending-indicator";
import {userFacingReadError} from "@/lib/user-facing-errors";

type ReadState = {attempt: number; description: string | null} |
  {attempt: number; status: number; code?: string};

function OriginalContent({jobId, href, rowId}: {jobId: string; href: string; rowId: string}) {
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<ReadState | null>(null);
  const current = state?.attempt === attempt ? state : null;
  useEffect(() => {
    const request = new AbortController();
    async function read() {
      try {
        const response = await fetch(`/api/jobs/${encodeURIComponent(jobId)}/original`, {signal: request.signal});
        const body = await response.json();
        if (request.signal.aborted) return;
        if (!response.ok) setState({attempt, status: response.status, code: body?.error?.code});
        else if (typeof body.description === "string" || body.description === null) setState({attempt, description: body.description});
        else setState({attempt, status: 502});
      } catch {
        if (!request.signal.aborted) setState({attempt, status: 503});
      }
    }
    void read();
    return () => request.abort();
  }, [attempt, jobId]);

  return <div className="stack-md">
    {!current ? <PendingIndicator label="正在读取岗位原文…" skeleton />
      : "status" in current ? <section className="jl-callout stack-sm" data-tone="warning">
          <div role="alert"><h3>未能读取岗位原文</h3>
            <p>{userFacingReadError(current.status, current.code, "暂时无法读取原文，可以重试；岗位列表和筛选仍保留。")}</p></div>
          {![401, 403, 404].includes(current.status) && <div><Button variant="secondary" onClick={() => setAttempt(attempt + 1)}>重新读取</Button></div>}
        </section>
      : current.description?.trim() ? <div className="jl-source-text" tabIndex={0}>{current.description}</div>
      : <section className="jl-callout stack-sm"><h3>还没有岗位原文</h3><p>可以打开岗位详情，补充招聘描述后再核对要求。</p></section>}
    <div><Button variant="secondary" asChild><OpenCatalogJob href={href} rowId={rowId} fromOriginal>打开完整岗位详情</OpenCatalogJob></Button></div>
  </div>;
}

export function JobOriginal({jobId, title, company, href, rowId}: {jobId: string; title: string; company: string; href: string; rowId: string}) {
  return <DetailDrawer trigger={<Button variant="subtle" id={`${rowId}-original`} aria-label={`查看 ${title} 的岗位原文`}>查看原文</Button>}
    title={title} description={`${company} · 岗位原文，不会重新分析`}>
    <OriginalContent jobId={jobId} href={href} rowId={rowId} />
  </DetailDrawer>;
}

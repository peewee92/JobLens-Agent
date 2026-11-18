"use client";

import {useEffect, useState} from "react";
import {existingMatchReportCopy, rankingPreflight, rankingScope} from "@/lib/agent-ranking-preflight";

const unavailable = "暂时无法核对已有匹配报告，请到岗位详情查看。";

/** One read-only check per batch, independent of the successful import receipt. */
export function useExistingMatchStatus(ids: readonly string[]) {
  const key = rankingScope([...new Set(ids)]);
  const [result, setResult] = useState<{key: string; messages: Map<string, string>} | null>(null);
  useEffect(() => {
    const jobs: string[] = JSON.parse(key);
    if (!jobs.length) return;
    const query = new URLSearchParams();
    jobs.forEach(id => query.append("jobId", id));
    const abort = new AbortController();
    const timeout = setTimeout(() => abort.abort(), 5000);
    let current = true;
    void fetch(`/api/match-ranking/preflight?${query}`, {cache: "no-store", signal: abort.signal})
      .then(async response => {
        if (!response.ok) throw new Error();
        const check = rankingPreflight(jobs, await response.json());
        if (current) setResult({key, messages: new Map(jobs.map(id => [id, existingMatchReportCopy(check, id)]))});
      })
      .catch(() => {if (current) setResult({key, messages: new Map()});})
      .finally(() => clearTimeout(timeout));
    return () => {current = false; clearTimeout(timeout); abort.abort();};
  }, [key]);
  return (id: string) => result?.key === key ? result.messages.get(id) ?? unavailable : "正在核对已有匹配报告…";
}

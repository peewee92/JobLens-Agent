"use client";
import React, {useEffect, useState} from "react";
import type {MatchReportHistoryItem} from "@/lib/contracts";
import {matchRecommendationLabels} from "@/lib/match-report";

/** Read the exact immutable report already bound by the runtime, never run matching. */
export function RankedJobExplanation({jobId, reportId, position}: {
  jobId: string; reportId: string; position: number;
}) {
  const [saved, setSaved] = useState<MatchReportHistoryItem | null>(null);
  const [failed, setFailed] = useState(false);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let active = true;
    setFailed(false);
    setSaved(null);
    void (async () => {
      try {
        const response = await fetch(`/api/jobs/${encodeURIComponent(jobId)}/match-reports/${encodeURIComponent(reportId)}`, {cache: "no-store"});
        if (!response.ok) throw new Error("report unavailable");
        const body = await response.json() as MatchReportHistoryItem;
        if (body.reportId !== reportId || body.report.jobId !== jobId) throw new Error("report identity mismatch");
        if (active) setSaved(body);
      } catch { if (active) setFailed(true); }
    })();
    return () => { active = false; };
  }, [jobId, reportId, retry]);
  if (failed) return <div role="status"><p>暂时无法读取本次排序依据，不会用最新结果替代；可以查看下方完整报告或重试。</p>
    <button type="button" className="button" onClick={() => setRetry(value => value + 1)}>重新读取排序依据</button></div>;
  if (!saved) return <p role="status">正在读取本次排序依据，不会调用模型…</p>;
  return <SavedRankedJobExplanation saved={saved} position={position} />;
}

export function SavedRankedJobExplanation({saved, position}: {saved: MatchReportHistoryItem; position: number}) {
  const report = saved.report;
  return <section className="detail-card" aria-label={`排序第 ${position} 项的依据`}>
    <p><strong>第 {position} 项 · {matchRecommendationLabels[report.recommendation]}</strong></p>
    <p>{report.summary}</p>
    {!saved.isCurrent && <p className="notice">这是本次排序的历史依据，当前事实已变化；请核对资料后重新分析，不能直接沿用旧建议。</p>}
    <p>已保存资料第 {report.profileVersion} 版 · 意向第 {report.searchIntentVersion ?? "未记录"} 版</p>
    {report.strengths.length ? <><h3>已有支持</h3><ul>{report.strengths.slice(0, 2).map(item =>
      <li key={item.requirementId}>{item.requirementText}<p>{item.reason}</p></li>)}</ul></> : <p>当前没有足够明确的核心优势证据。</p>}
    {report.risks.length ? <><h3>关键未知与风险</h3><ul>{report.risks.slice(0, 2).map(item =>
      <li key={item.requirementId}>{item.requirementText}<p>{item.reason}</p></li>)}</ul></> : <p>当前报告未列出额外岗位风险，不代表所有条件都已验证。</p>}
    <p className="muted">排序位置不是录用概率；完整要求、证据和偏好检查见下方报告。</p>
  </section>;
}

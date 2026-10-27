import React from "react";
import Link from "next/link";
import {AnalysisExecutionControls} from "./analysis-execution-controls";
import type {SavedCareerAnalysis} from "@/lib/contracts";
import {formatDateTime} from "@/lib/format";

const evidenceLabels: Record<string, string> = {
  missing: "尚无对应技能记录（不代表不会）", unevidenced: "已有技能记录，证据待补充",
  supported: "已有证据支持", evidenced: "已有证据支持", partial: "证据部分覆盖",
};

export function SavedCareerAnalysisView({result, backHref}: {result: SavedCareerAnalysis; backHref: string}) {
  return <>
    <section className="page-heading"><p className="eyebrow">已保存分析 · 版本 {result.schemaVersion}</p>
      <h1>本次目标岗位的差距与准备材料</h1>
      <p>保存于 {formatDateTime(result.createdAt)}。以下是当时的事实与结论，不会在打开时重新生成。</p>
      <Link href={backHref}>返回本次运行</Link>
    </section>
    <section className="card stack-md" aria-label="分析事实版本">
      <h2>{result.isCurrent ? "事实版本仍适用于当前资料" : "历史材料：当前事实已变化"}</h2>
      {!result.isCurrent && <p className="notice">保留原始材料，但不要将它当作当前建议。请返回运行，使用最新确认的事实新建分析。</p>}
      <p>职业资料 v{result.profileVersion} · 求职意向 v{result.searchIntentVersion} · {result.selectedJobIds.length} 个确认目标</p>
      <details><summary>查看事实标识、策略和变化原因</summary>
        <p>资料：{result.profileId}；意向：{result.searchIntentId}</p>
        <ul>{result.bindings.map(item => <li key={item.jobId}>{item.title} · {item.company}：要求 {item.extractionId} · 报告 {item.matchReportId} · {item.policyVersion}</li>)}</ul>
        {result.staleReasons.length > 0 && <p>原因码：{result.staleReasons.join("、")}</p>}
      </details>
    </section>
    {result.updatePartial && <section className="card stack-md" aria-label="部分范围说明"><h2>这是一份部分范围分析</h2>
      <p>用户明确选择只使用已完成岗位；以下岗位没有在本次完成分析，不代表已不适合：{result.unanalysedJobIds?.join("、")}。</p>
      <Link href={backHref}>查看未完成步骤与原因</Link></section>}
    {result.updateSourceThreadId && <section className="card stack-md"><h2>对比原分析</h2>
      <p>核对同一范围下推荐、证据覆盖和目标选择的变化；结论未变也是合法结果。</p>
      <Link href={`/agent/results/${encodeURIComponent(result.threadId)}/comparison`}>查看新旧结果与变化原因</Link></section>}
    <section className="card stack-md"><h2>根据新事实更新分析</h2><p>先检查原目标或原批次的输入与可复用结果；查看预检不会调用模型或覆盖本次材料。</p>
      <Link href={`/agent/results/${encodeURIComponent(result.threadId)}/update`}>查看更新范围与输入</Link>
    </section>
    <AnalysisExecutionControls threadId={result.threadId} resultId={result.resultId}
      jobIds={result.selectedJobIds} isCurrent={result.isCurrent}
      jobLabels={Object.fromEntries(result.bindings.map(item => [item.jobId, item.title]))} />
    <section className="card stack-md"><h2>差距与补齐标准</h2>
      <p className="muted">差距表示当前资料和证据的覆盖情况，不是对你真实能力的否定。</p>
      {result.gaps.items.length === 0 ? <p>本次没有可列出的能力差距，不代表已经满足全部岗位要求。</p> :
        result.gaps.items.map((item, index) => <article className="card stack-sm" key={`${item.capability}-${index}`}>
          <h3>{item.priority} · {item.capability}</h3><p>{item.currentState}</p>
          <p className="muted">依据：{item.supportingJobIds.length} 个岗位 · 要求 {item.supportingRequirementIds.join("、")} · 个人证据 {item.evidenceIds.join("、") || "尚未覆盖"}</p>
          <ul>{item.completionCriteria.map((criterion, i) => <li key={i}>{criterion}</li>)}</ul>
        </article>)}
    </section>
    {result.preparations.map(preparation => {
      const binding = result.bindings.find(item => item.jobId === preparation.jobId);
      return <section className="card stack-md" key={preparation.jobId}>
        <h2>{binding?.title ?? preparation.jobId} · 准备材料</h2>
        <p>{binding?.company}</p>
        {binding && <Link href={`/jobs/${encodeURIComponent(binding.jobId)}?reportId=${encodeURIComponent(binding.matchReportId)}`}>查看当时的匹配依据</Link>}
        <h3>简历可用事实要点</h3>
        <p className="muted">以下不是完整简历，也不增加未经确认的经历。</p>
        {preparation.resumeDelta?.highlights.length ? <ul>{preparation.resumeDelta.highlights.map((item, i) =>
          <li key={i}>{item.capability} · 要求 {item.requirementId} · 证据 {item.evidenceIds.join("、")}</li>)}</ul> : <p>当前没有足够证据形成事实要点。</p>}
        <h3>仍需核实或补充</h3>
        {!preparation.resumeDelta?.evidenceGaps.length && <p>本次未列出技能证据缺口，仍请逐项核对岗位条件。</p>}
        <ul>{preparation.resumeDelta?.evidenceGaps.map((item, i) => <li key={i}>{item.capability}：{evidenceLabels[item.status] ?? "证据待核实"}</li>)}</ul>
        <h3>面试问题与证据提示</h3>
        <p className="muted">围绕岗位要求准备说明，不是面试能力评分。</p>
        <ul>{preparation.interviewFacts?.items.map((item, i) => <li key={i}>
          如何用真实经历说明“{item.requirementText}”？
          <p>{item.evidenceSummaries.length ? item.evidenceSummaries.join("；") : "暂无可引用的经历，请如实说明并核实。"}</p>
          <p className="muted">要求 {item.requirementId} · 证据 {item.evidenceIds.join("、") || "待补充"}</p>
        </li>)}</ul>
        <h3>建议行动与完成标准</h3>
        {!preparation.studyChecklist?.items.length && <p>当前没有证据缺口驱动的补充行动；实际投递与面试安排仍由你决定。</p>}
        <ul>{preparation.studyChecklist?.items.slice(0, 3).map((item, i) => <li key={i}>{item.capability} · {item.requirementText}
          <ul>{item.completionCriteria.map((criterion, j) => <li key={j}>{criterion}</li>)}</ul></li>)}</ul>
        {(preparation.studyChecklist?.items.length ?? 0) > 3 && <details><summary>展开其余行动</summary><ul>
          {preparation.studyChecklist?.items.slice(3).map((item, i) => <li key={i}>{item.capability}<ul>{item.completionCriteria.map((criterion, j) => <li key={j}>{criterion}</li>)}</ul></li>)}
        </ul></details>}
        <details><summary>已保存的经历事实</summary><ul>{preparation.storyFacts?.items.map((item, i) =>
          <li key={i}>{item.evidenceSummary} · 证据 {item.evidenceId}</li>)}</ul></details>
      </section>;
    })}
  </>;
}

import React from "react";
import Link from "next/link";
import {Button} from "./ui/button";
import {PageHeading} from "./ui/patterns";
import {Badge, Panel} from "./ui/primitives";
import {currentStateLabel, completionCriterionLabel, gapImportanceLabel, gapNextStep} from "@/lib/gap-language";
import {UnrankedJobs} from "./unranked-jobs";
import {AnalysisExecutionControls} from "./analysis-execution-controls";
import type {SavedCareerAnalysis} from "@/lib/contracts";
import {formatDateTime} from "@/lib/format";
import {preparationFacts} from "@/lib/preparation-facts";
import type {RankingOmission} from "@/lib/agent-ranking-preflight";
import {reportStaleReasonLabel} from "@/lib/match-report";

const evidenceLabels: Record<string, string> = {
  missing: "尚无对应技能记录（不代表不会）", unevidenced: "已有技能记录，证据待补充",
  supported: "已有证据支持", evidenced: "已有证据支持", partial: "证据部分覆盖",
};

export function SavedCareerAnalysisView({result, backHref, savedScope, additionalLabels = {}, currentOmissions, savedPartialSupport = {}, savedMatchedSupport = {}}: {
  result: SavedCareerAnalysis; backHref: string;
  savedScope?: {requested: readonly string[]; compared: number};
  additionalLabels?: Record<string, string>; currentOmissions?: RankingOmission[];
  savedPartialSupport?: Record<string, readonly string[]>;
  savedMatchedSupport?: Record<string, readonly string[]>;
}) {
  const labels = {...additionalLabels, ...Object.fromEntries(result.bindings.map(item => [item.jobId, item.title]))};
  const preparedFacts = result.preparations.map(preparationFacts);
  const requirements = new Map(preparedFacts.flatMap(item => [...item.requirements]));
  const importance = new Map([...requirements].map(([id, item]) => [id, item.importance]));
  const matchHref = (binding: SavedCareerAnalysis["bindings"][number]) =>
    `/jobs/${encodeURIComponent(binding.jobId)}?reportId=${encodeURIComponent(binding.matchReportId)}#job-match-report`;
  return <div className="saved-analysis">
    <PageHeading kicker="第 3 步 · 比较并准备" title="本次目标岗位的差距与准备材料"
      description={`保存于 ${formatDateTime(result.createdAt)}。以下是当时的事实与结论，不会在打开时重新生成。`} />
    <Panel className="stack-sm" aria-labelledby="saved-scope-heading">
      <Badge tone={result.isCurrent ? "success" : "warning"}>{result.isCurrent ? "已保存 · 当前可用" : "历史记录 · 只读"}</Badge>
      <h2 id="saved-scope-heading">{result.isCurrent ? "这些材料仍适用于当前资料" : "历史材料：当前事实已变化"}</h2>
      {savedScope && <p className="jl-scope-count">已选 {savedScope.requested.length} 个岗位，实际比较 {savedScope.compared} 个；你确认了 {result.selectedJobIds.length} 个准备目标。</p>}
      {result.selectedJobIds.length > 0 && <p>准备目标：{result.selectedJobIds.map(id => labels[id] ?? "名称暂不可读取").join("、")}</p>}
      {!result.isCurrent && <p>保留原始材料，但不要将它当作当前建议。请先核对当前事实，再创建独立的新分析。</p>}
      {!result.isCurrent && result.staleReasons.length > 0 && <ul>{result.staleReasons.map(reason => {
        const separator = reason.indexOf(":");
        const jobId = separator < 0 ? null : reason.slice(0, separator);
        const code = separator < 0 ? reason : reason.slice(separator + 1);
        const job = result.bindings.find(item => item.jobId === jobId);
        return <li key={reason}>{job ? `${job.title}：` : ""}{reportStaleReasonLabel(code)}</li>;
      })}</ul>}
      <div className="jl-inline">
        {!result.isCurrent
          ? <Button asChild><Link href={`/agent/results/${encodeURIComponent(result.threadId)}/update`}>先核对更新范围</Link></Button>
          : result.selectedJobIds.length > 0 && <Button asChild><a href="#start-preparation">开始准备行动</a></Button>}
        <Link className="jl-text-link" href={backHref}>返回本次比较</Link>
      </div>
      <details><summary>查看依据版本与变化原因</summary>
        <p>结果格式第 {result.schemaVersion} 版 · 资料 {result.profileId} 第 {result.profileVersion} 版 · 意向 {result.searchIntentId} 第 {result.searchIntentVersion} 版</p>
        <ul>{result.bindings.map(item => <li key={item.jobId}>{item.title} · {item.company}：要求 {item.extractionId} · 报告 {item.matchReportId} · {item.policyVersion}</li>)}</ul>
        {result.staleReasons.length > 0 && <p>原因码：{result.staleReasons.join("、")}</p>}
      </details>
    </Panel>
    <nav className="jl-inline jl-job-outline" aria-label="跳到准备材料">
      <a href="#saved-gaps">看能力差距</a>
      {result.preparations.length > 0 && <><a href="#saved-resume-0">看简历建议</a>
        <a href="#saved-interview-0">看面试问题</a></>}
    </nav>
    {result.preparations.length > 1 && <ul>{result.preparations.map((item, index) =>
      <li key={item.jobId}>{labels[item.jobId] ?? "目标岗位"} · <a href={`#saved-resume-${index}`}>简历建议</a> · <a href={`#saved-interview-${index}`}>面试问题</a></li>)}</ul>}
    <UnrankedJobs ids={result.unrankedJobIds ?? []} labels={labels} scope={savedScope?.requested} currentOmissions={currentOmissions} />
    {result.updatePartial && <section className="card stack-md" aria-label="部分范围说明"><h2>这是一份部分范围分析</h2>
      <p>用户明确选择只使用已完成岗位；以下岗位没有在本次完成分析，不代表已不适合：{result.unanalysedJobIds?.map(id => labels[id] ?? "名称暂不可读取").join("、")}。</p>
      <Link href={backHref}>查看未完成步骤与原因</Link></section>}
    <section className="card stack-md" id="saved-gaps" tabIndex={-1}><h2>能力差距：先核实经历，再决定怎么准备</h2>
      <p className="muted">这里显示哪些岗位要求还没有被你的已确认经历覆盖。不是能力评分，不因资料缺失就认定你不会。</p>
      {result.gaps.items.length === 0 ? <p>本次没有可列出的能力差距，不代表已经满足全部岗位要求。</p> :
        result.gaps.items.map((item, index) => {
          const partiallySupported = result.bindings.filter(binding => item.supportingJobIds.includes(binding.jobId)
            && item.supportingRequirementIds.some(id => savedPartialSupport[binding.jobId]?.includes(id)));
          return <article className="jl-gap-item stack-sm" key={`${item.capability}-${index}`}>
          <h3>{item.capability}</h3>
          <p><strong>{gapImportanceLabel(item.whyImportant.mustHaveRatio, item.supportingRequirementIds, importance)}</strong></p>
          <p>{partiallySupported.length > 0 ? "还没有确认经历能覆盖全部要求。" : currentStateLabel(item.currentState)}</p>
          {partiallySupported.length > 0 && <div className="notice">
            <p>当时的匹配找到了相关经历，但只覆盖了部分要求；其余条件仍需要核实。</p>
            <ul>{partiallySupported.map(binding => <li key={binding.jobId}><Link href={matchHref(binding)}>
              查看「{binding.title}」当时的匹配依据
            </Link></li>)}</ul>
          </div>}
          <p><strong>下一步：</strong>{gapNextStep(item.whyImportant.mustHaveRatio)}</p>
          <p>涉及岗位：{item.supportingJobIds.map(id => labels[id]).filter(Boolean).join("、") || "名称暂不可读取"}</p>
          {!!item.supportingRequirementIds.length && <p>岗位依据：{item.supportingRequirementIds.map(id => requirements.get(id)?.text).filter(Boolean).join("；") || "可在下方的匹配依据里核对原文。"}</p>}
          <details><summary>查看来源证据</summary><p className="muted">依据：{item.supportingJobIds.length} 个岗位 · 要求 {item.supportingRequirementIds.join("、")} · 个人证据 {item.evidenceIds.join("、") || "尚未覆盖"}</p></details>
          <p><strong>如果你确实有相关经历，核对以下两点：</strong></p>
          <ul>{item.completionCriteria.map((criterion, i) => <li key={i}>{completionCriterionLabel(criterion)}</li>)}</ul>
        </article>;
        })}
    </section>
    {result.preparations.map((preparation, index) => {
      const binding = result.bindings.find(item => item.jobId === preparation.jobId);
      const facts = preparedFacts[index];
      const partial = savedPartialSupport[preparation.jobId] ?? [];
      const matched = savedMatchedSupport[preparation.jobId] ?? [];
      return <section className="card stack-md" key={preparation.jobId}>
        <h2>{binding?.title ?? "目标岗位"} · 准备材料</h2>
        <p>{binding?.company}</p>
        {binding && <Link href={matchHref(binding)}>查看当时的匹配依据</Link>}
        <h3 id={`saved-resume-${index}`} tabIndex={-1}>简历可用事实要点</h3>
        <p className="muted">以下不是完整简历，主要列出已与技能关联的事实。其他相关工作和项目可到当时的匹配依据里核对；不会自动写进简历。</p>
        {preparation.resumeDelta?.highlights.length ? <ul>{preparation.resumeDelta.highlights.map((item, i) =>
          <li key={i}><strong>{item.capability}</strong>
            {facts.requirements.get(item.requirementId)?.text && <p>对应岗位要求：{facts.requirements.get(item.requirementId)?.text}</p>}
            <p>{item.evidenceIds.map(id => facts.evidenceSummaries.get(id)).filter(Boolean).join("；") || "已关联真实经历，可按下方来源核对；此材料未提供可展示的经历摘要。"}</p>
            <details><summary>查看事实来源</summary>要求 {item.requirementId} · 证据 {item.evidenceIds.join("、")}</details></li>)}</ul> : <p>当前没有足够证据形成事实要点。</p>}
        <h3>仍需核实或补充</h3>
        {!preparation.resumeDelta?.evidenceGaps.length && <p>本次未列出技能证据缺口，仍请逐项核对岗位条件。</p>}
        <ul>{preparation.resumeDelta?.evidenceGaps.map((item, i) => <li key={i}>{item.capability}：{evidenceLabels[item.status] ?? "证据待核实"}</li>)}</ul>
        <h3 id={`saved-interview-${index}`} tabIndex={-1}>面试问题与证据提示</h3>
        <p className="muted">围绕岗位要求准备说明，不是面试能力评分。</p>
        <ul>{preparation.interviewFacts?.items.map((item, i) => <li key={i}>
          <p><strong>招聘原文：</strong>{item.requirementText}</p>
          <p>你做过哪些相关的事？当时是怎么做的，结果如何？</p>
          {item.evidenceSummaries.length > 0 && <p>{item.evidenceSummaries.join("；")}</p>}
          {partial.includes(item.requirementId) && binding
            ? <p>已有相关经历，只覆盖部分要求。<Link href={matchHref(binding)}>核对当时用了哪些经历</Link>，没做过的部分请如实说明。</p>
            : item.evidenceSummaries.length === 0 && (matched.includes(item.requirementId) && binding
              ? <p>当时的匹配找到了已确认经历，这份面试材料没有直接引用。<Link href={matchHref(binding)}>查看当时的匹配依据</Link>，准备时请按实际经历说明。</p>
              : <p>此准备材料没有可直接引用的经历。请核对自己的实际经历，不要补写没做过的事。</p>)}
          <details><summary>查看问题依据</summary>要求 {item.requirementId} · 证据 {item.evidenceIds.join("、") || (matched.includes(item.requirementId) || partial.includes(item.requirementId) ? "参见当时的匹配依据" : "待补充")}</details>
        </li>)}</ul>
        <h3>建议行动与完成标准</h3>
        {!preparation.studyChecklist?.items.length && <p>当前没有证据缺口驱动的补充行动；实际投递与面试安排仍由你决定。</p>}
        <ul>{preparation.studyChecklist?.items.slice(0, 3).map((item, i) => <li key={i}>{item.capability} · {item.requirementText}
          <p><strong>如果你确实有相关经历，核对以下两点：</strong></p>
          <ul>{item.completionCriteria.map((criterion, j) => <li key={j}>{completionCriterionLabel(criterion)}</li>)}</ul></li>)}</ul>
        {(preparation.studyChecklist?.items.length ?? 0) > 3 && <details><summary>展开其余行动</summary><ul>
          {preparation.studyChecklist?.items.slice(3).map((item, i) => <li key={i}>{item.capability}<ul>{item.completionCriteria.map((criterion, j) => <li key={j}>{completionCriterionLabel(criterion)}</li>)}</ul></li>)}
        </ul></details>}
        <details><summary>已保存的经历事实</summary><ul>{preparation.storyFacts?.items.map((item, i) =>
          <li key={i}>{item.evidenceSummary}</li>)}</ul></details>
      </section>;
    })}

    {result.updateSourceThreadId && <section className="card stack-md"><h2>对比原分析</h2>
      <p>核对同一范围下推荐、证据覆盖和目标选择的变化；结论未变也是合法结果。</p>
      <Link href={`/agent/results/${encodeURIComponent(result.threadId)}/comparison`}>查看新旧结果与变化原因</Link></section>}
    <section className="card stack-md"><h2>根据新事实更新分析</h2><p>先检查原目标或原批次的输入与可复用结果；查看预检不会调用模型或覆盖本次材料。</p>
      <Link href={`/agent/results/${encodeURIComponent(result.threadId)}/update`}>查看更新范围与输入</Link>
    </section>
    <div id="start-preparation" tabIndex={-1}><AnalysisExecutionControls threadId={result.threadId} resultId={result.resultId}
      jobIds={result.selectedJobIds} isCurrent={result.isCurrent} isUpdate={Boolean(result.updateSourceThreadId)}
      jobLabels={labels} /></div>
  </div>;
}

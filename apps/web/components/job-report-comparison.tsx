import type {MatchReportHistoryItem} from "@/lib/contracts";
import {requirementFitLabels} from "@/lib/eligibility";
import {formatDateTime} from "@/lib/format";
import {matchRecommendationLabels} from "@/lib/match-report";

import {requirementCoverage, coverageLabels} from "@/lib/match-coverage";

/** Compare saved snapshots only; never claim causality from version changes. */
export function JobReportComparison({previous, current}: {previous: MatchReportHistoryItem; current: MatchReportHistoryItem}) {
  const before = previous.report;
  const after = current.report;
  if (before.jobId !== after.jobId) return null;
  const comparable = Boolean(before.policyVersion && after.policyVersion &&
    before.policyVersion === after.policyVersion && before.retrievalVersion && before.retrievalVersion === after.retrievalVersion && before.extractionId && before.extractionId === after.extractionId);
  const intentUnknown = !before.searchIntentId || !after.searchIntentId || before.searchIntentVersion == null || after.searchIntentVersion == null;
  const intentChanged = before.searchIntentId !== after.searchIntentId || before.searchIntentVersion !== after.searchIntentVersion;
  const methodChanged = before.matcherVersion !== after.matcherVersion || before.promptVersion !== after.promptVersion || before.model !== after.model;
  const prior = new Map(before.requirementResults.map(item => [item.requirementId, item]));
  const next = new Map(after.requirementResults.map(item => [item.requirementId, item]));
  const sameRequirements = prior.size === before.requirementResults.length && next.size === after.requirementResults.length &&
    prior.size === next.size && [...prior.keys()].every(id => next.has(id));
  const changed = after.requirementResults.filter(item => {
    const old = prior.get(item.requirementId);
    return !old || old.assessmentSource !== item.assessmentSource || old.candidateCount !== item.candidateCount || old.semanticVerdict !== item.semanticVerdict || old.eligibilityStatus !== item.eligibilityStatus ||
      old.reason !== item.reason || [...old.evidenceIds].sort().join("\0") !== [...item.evidenceIds].sort().join("\0");
  });
  return <section className="notice" aria-label="同一岗位的新旧报告">
    <h3>与上一份报告核对</h3>
    <p>上一份：{formatDateTime(previous.createdAt)} · 资料第 {before.profileVersion} 版 · {matchRecommendationLabels[before.recommendation]}</p>
    <p>这份：{formatDateTime(current.createdAt)} · 资料第 {after.profileVersion} 版 · {matchRecommendationLabels[after.recommendation]}{current.isCurrent ? "（当前）" : "（历史）"}</p>
    {!comparable ? <p>两份报告的岗位要求版本、匹配规则或证据检索规则不同，或版本未记录；不能直接比较逐项判断。请分别查看原报告。</p> : !sameRequirements ? <p>两份报告保存的要求明细不一致，不能直接比较逐项判断。请分别查看原报告。</p> : prior.size === 0 ? <p>两份报告没有可比较的要求明细，不能据此判断要求覆盖是否变化。</p> : <>
      {changed.length ? <ul>{changed.map(item => {
        const old = prior.get(item.requirementId)!;
        return <li key={item.requirementId}><strong>{item.originalText}</strong>
          <p>{coverageLabels[requirementCoverage(old)]} → {coverageLabels[requirementCoverage(item)]} · 证据 {old.evidenceIds.length} 条 → {item.evidenceIds.length} 条</p>
          <p>基础条件：{requirementFitLabels[old.eligibilityStatus]} → {requirementFitLabels[item.eligibilityStatus]}</p>
          <p>之前：{old.reason}</p><p>现在：{item.reason}</p></li>;
      })}</ul> : <p>已保存的逐项判断、原因和证据引用没有变化；这不代表资料或求职偏好完全相同。</p>}
    </>}
    {intentUnknown ? <p>至少一份报告未记录完整的求职意向版本，无法确认两次偏好输入是否一致。</p> : intentChanged && <p>两次使用的求职意向不同或版本记录不同，推荐变化不能只归因于经历。</p>}
    {methodChanged && <p>两次使用的匹配方法或模型记录不同，结论变化不能只归因于经历。</p>}
    <p>这里只对照保存的结果，不推断变化原因；岗位条件等其他输入也可能变化。证据未覆盖不等于不会，也不等于满足。</p>
  </section>;
}

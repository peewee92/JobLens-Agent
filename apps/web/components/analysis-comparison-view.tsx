import React from 'react';
import Link from 'next/link';
import type {AnalysisComparison, AnalysisChange} from '@/lib/contracts';
const changes: Record<AnalysisChange, string> = {improved: '判断改善', weakened: '判断变弱', unchanged: '结论未变', mixed: '有改善也有变弱', not_comparable: '不能直接比较', unavailable: '缺少本次或历史依据'};
const recommendations: Record<string, string> = {strong: '优先投入（核心证据强）', good: '优先投入', stretch: '挑战／待核实', low: '证据不足', blocked: '暂不建议（明确硬冲突）'};
const coverage: Record<string, string> = {supported: '已有证据支持', partial: '部分支持', unverified: '待核实／证据未覆盖', hard_conflict: '明确硬冲突'};
const reasons: Record<string, string> = {
  profile_changed: '职业资料版本发生变化', intent_changed: '求职意向版本发生变化', targets_changed: '确认的目标集合发生变化，不能直接比较汇总差距数量',
  ranking_scope_not_comparable: '排序参与岗位或可比较依据不完整，不比较名次升降', requirements_changed: '岗位要求版本不同，请分别查看两次要求，不能当成个人能力升降',
  policy_changed: '匹配规则版本不同，不给出改善或变差结论', judgment_method_changed: '匹配方法、提示词或模型不同，不能只把变化归因于新增事实',
  requirement_snapshot_mismatch: '同一要求的保存内容不一致，不能直接比较', preference_judgment_changed: '保存的求职偏好判断发生变化',
  current_not_analysed: '本次没有完成这个岗位的分析，不代表已经淘汰', historical_not_saved: '原分析没有保存该岗位报告的明确引用，不能用最新报告补造历史',
  current_report_missing: '本次绑定的归档报告无法读取', historical_report_missing: '原分析绑定的归档报告无法读取',
  evidence_references_changed: '引用的经历证据或个人事实发生变化；引用变更不等于能力增加',
  conclusion_improved: '同版本要求与规则下，推荐或证据覆盖判断有所改善', conclusion_weakened: '同版本要求与规则下，推荐或证据覆盖判断有所变弱',
  conclusion_mixed: '不同维度变化方向不一致，需要逐项核对', conclusion_unchanged: '增加或调整资料后，本岗位的推荐与证据覆盖判断仍未变',
};
export function AnalysisComparisonView({comparison: c}: {comparison: AnalysisComparison}) {
  const resultHref = (thread: string) => `/agent/results/${encodeURIComponent(thread)}`;
  const title = (id: string) => c.items.find(i => i.jobId === id)?.title ?? id;
  return <div className="analysis-comparison">
    <section className="page-heading"><p className="eyebrow">更新分析 · 保存结果比较</p><h1>新事实之后，结论发生了什么变化</h1>
      <p>范围：{c.scope === 'targets' ? '原确认目标' : '原分析整批'} · {c.requestedJobIds.length} 个岗位。职业资料 v{c.previousProfileVersion} → v{c.currentProfileVersion}；求职意向 v{c.previousIntentVersion} → v{c.currentIntentVersion}。</p>
      <div className="actions"><Link className="button-secondary" href={resultHref(c.sourceThreadId)}>打开原始保存结果</Link><Link className="button-secondary" href={resultHref(c.threadId)}>打开本次保存结果</Link></div>
    </section>
    <section className="panel"><h2>先看比较边界</h2>
      <p>只读取两次保存结果和明确绑定的报告，不重新匹配、不调用模型、不读取最新资料来补造历史。改善表示保存的判断变化，不是录用概率，也不承诺能力提升。</p>
      {c.partial && <p className="notice">本次仅使用了用户明确接受的部分岗位，未完成项仍列在下面，不计入改善统计。</p>}
      <ul>{c.reasonCodes.map(code => <li key={code}>{reasons[code] ?? code}</li>)}</ul>
      <p>目标新增：{c.addedTargetIds.map(title).join('、') || '无'}；目标移出：{c.removedTargetIds.map(title).join('、') || '无'}。这是目标选择变化，不是能力评分。</p>
    </section>
    {c.items.map(item => <section className="panel" key={item.jobId}>
      <h2>{item.title} · {changes[item.signal]}</h2>
      <p>推荐：{item.previousRecommendation ? recommendations[item.previousRecommendation] ?? item.previousRecommendation : '无保存依据'} → {item.currentRecommendation ? recommendations[item.currentRecommendation] ?? item.currentRecommendation : '本次无可用依据'}。</p>
      <p>推荐变化：{changes[item.recommendationChange]}；证据覆盖变化：{changes[item.coverageChange]}。</p>
      {item.rankChange !== null ? <p>同范围排序：第 {item.previousRank} → 第 {item.currentRank}；{item.rankChange > 0 ? `上移 ${item.rankChange} 位` : item.rankChange < 0 ? `下移 ${-item.rankChange} 位` : '位置未变'}。</p> : <p>本岗位不比较名次升降；不把缺失或未完成当作排名下降。</p>}
      <ul>{item.reasonCodes.map(code => <li key={code}>{reasons[code] ?? code}</li>)}</ul>
      <div className="actions">
        {item.previousReportId && <Link className="button-secondary" href={`/jobs/${encodeURIComponent(item.jobId)}?reportId=${encodeURIComponent(item.previousReportId)}`}>查看原报告依据</Link>}
        {item.currentReportId && <Link className="button-secondary" href={`/jobs/${encodeURIComponent(item.jobId)}?reportId=${encodeURIComponent(item.currentReportId)}`}>查看本次报告依据</Link>}
      </div>
      {item.requirements.length > 0 && <details><summary>逐项核对已保存的要求与证据判断</summary>
        {item.requirements.map(r => <article key={r.requirementId} className="eligibility-result-card"><h3>{r.originalText}</h3>
          <p>{coverage[r.previousCoverage] ?? r.previousCoverage} → {coverage[r.currentCoverage] ?? r.currentCoverage} · {changes[r.change]}</p>
          <p>原判断：{r.previousReason}</p><p>本次判断：{r.currentReason}</p>
          <p>原证据：{r.previousEvidenceIds.join('、') || '无引用'}；本次证据：{r.currentEvidenceIds.join('、') || '无引用'}。</p>
          <p>原个人事实：{r.previousFactRefs.join('、') || '无引用'}；本次个人事实：{r.currentFactRefs.join('、') || '无引用'}。</p>
          <p>要求标识：{r.requirementId}</p></article>)}
      </details>}
      {item.preferences.length > 0 && <details><summary>核对两次保存的求职偏好判断</summary><ul>{item.preferences.map(p => <li key={p.key}>原：{p.previousReason ?? '无记录'}；本次：{p.currentReason ?? '无记录'}。</li>)}</ul></details>}
      <details><summary>核对版本与原因码</summary><p>岗位：{item.jobId}；要求：{item.previousExtractionId ?? '缺失'} → {item.currentExtractionId ?? '缺失'}；规则：{item.previousPolicyVersion ?? '缺失'} → {item.currentPolicyVersion ?? '缺失'}。</p><p>{item.reasonCodes.join('、')}</p></details>
    </section>)}
  </div>;
}

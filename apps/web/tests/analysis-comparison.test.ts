import assert from 'node:assert/strict';
import test from 'node:test';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {AnalysisComparisonView} from '../components/analysis-comparison-view';
import type {AnalysisComparison} from '../lib/contracts';

const comparison: AnalysisComparison = {
  comparisonVersion: 1, sourceThreadId: 'original', sourceResultId: 'old', threadId: 'updated', resultId: 'new', scope: 'batch',
  previousProfileVersion: 1, currentProfileVersion: 2, previousIntentVersion: 1, currentIntentVersion: 1,
  requestedJobIds: ['j1','j2'], rankingComparable: false, partial: true, reasonCodes: ['profile_changed','ranking_scope_not_comparable'],
  addedTargetIds: [], removedTargetIds: [], items: [{
    jobId: 'j1', title: '后端工程师', previousReportId: 'old-report', currentReportId: 'new-report',
    previousExtractionId: 'extract', currentExtractionId: 'extract', previousPolicyVersion: 'v3', currentPolicyVersion: 'v3',
    previousRecommendation: 'stretch', currentRecommendation: 'stretch', previousRank: 1, currentRank: 1, rankChange: null,
    signal: 'unchanged', recommendationChange: 'unchanged', coverageChange: 'unchanged', reasonCodes: ['evidence_references_changed','conclusion_unchanged'],
    requirements: [{requirementId: 'req1', originalText: 'Python 开发', previousCoverage: 'unverified', currentCoverage: 'unverified',
      previousReason: '没有已确认依据', currentReason: '新证据仍未覆盖该要求', previousEvidenceIds: [], currentEvidenceIds: ['e2'], previousFactRefs: [], currentFactRefs: [], change: 'unchanged'}], preferences: [],
  }, {
    jobId: 'j2', title: '平台工程师', previousReportId: 'old2', currentReportId: null, previousExtractionId: 'ext2', currentExtractionId: null,
    previousPolicyVersion: 'v3', currentPolicyVersion: null, previousRecommendation: 'strong', currentRecommendation: null,
    previousRank: 2, currentRank: null, rankChange: null, signal: 'unavailable', recommendationChange: 'unavailable', coverageChange: 'unavailable',
    reasonCodes: ['current_not_analysed'], requirements: [], preferences: [],
  }],
};
test('comparison shows actual boundaries, evidence and exact historical report links', () => {
  const html = renderToStaticMarkup(React.createElement(AnalysisComparisonView, {comparison}));
  for (const text of ['结论未变','不重新匹配','引用变更不等于能力增加','未完成项','不代表已经淘汰','待核实／证据未覆盖',
    'new-report','old-report','/agent/results/original','原判断：','本次判断：','e2']) assert.ok(html.includes(text), text);
  assert.doesNotMatch(html, /位置未变|上移|下移/);
});
test('incompatible requirements do not claim improvement or rank movement', () => {
  const c = {...comparison, partial: false, items: [{...comparison.items[0], signal: 'not_comparable' as const,
    recommendationChange: 'not_comparable' as const, coverageChange: 'not_comparable' as const, requirements: [], reasonCodes: ['requirements_changed']}]};
  const html = renderToStaticMarkup(React.createElement(AnalysisComparisonView, {comparison: c}));
  assert.ok(html.includes('岗位要求版本不同'));
  assert.doesNotMatch(html, /有所改善|位置未变|上移|下移/);
});

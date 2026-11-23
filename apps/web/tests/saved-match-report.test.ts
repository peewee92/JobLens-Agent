import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import {renderToStaticMarkup} from "react-dom/server";
import {SavedMatchReportNotice} from "../components/saved-match-report-notice";
import {MatchReportRequirementDetails} from "../components/job-match-report-panel";
import {reportStaleReasonLabel} from "../lib/match-report";
import type {MatchReportHistoryItem} from "../lib/contracts";

function result(isCurrent: boolean): MatchReportHistoryItem {
  return {
    reportId: "saved-original", createdAt: "2026-10-25T00:00:00Z", isCurrent,
    staleReasons: isCurrent ? [] : ["profile_changed", "policy_changed"],
    report: {profileVersion: 2, searchIntentVersion: 1, policyVersion: "match-policy-v2", extractionId: "original-extraction"} as MatchReportHistoryItem["report"],
  };
}

test("historical report explains changes without claiming the original is current", () => {
  const html = renderToStaticMarkup(React.createElement(SavedMatchReportNotice, {result: result(false)}));
  assert.match(html, /历史结果：不再用于当前排序/);
  assert.match(html, /职业资料已更新/);
  assert.match(html, /旧结果不会被覆盖/);
  assert.match(html, /original-extraction/);
  assert.match(html, /match-policy-v2/);
  assert.doesNotMatch(html, /已保存的当前结果/);
});

test("current snapshot shows saved versions, not an invitation to rerun automatically", () => {
  const html = renderToStaticMarkup(React.createElement(SavedMatchReportNotice, {result: result(true)}));
  assert.match(html, /已保存的当前结果/);
  assert.doesNotMatch(html, /历史结果：/);
});

test("unknown reason stays understandable and does not expose raw server codes", () => {
  assert.equal(reportStaleReasonLabel("future-private-code"), "分析输入已变化，请核实后更新分析");
});

test("changed job description is explained as a requirement re-analysis", () => {
  assert.match(reportStaleReasonLabel("job_description_changed"), /岗位描述已变化/);
  assert.match(reportStaleReasonLabel("job_description_changed"), /重新分析岗位要求/);
});

test("unavailable job description is not called a confirmed change", () => {
  const message = reportStaleReasonLabel("job_description_unavailable");
  assert.match(message, /无法核实/);
  assert.doesNotMatch(message, /已变化/);
});

test("the saved report exposes every frozen explanation, not just the three featured insights", () => {
  const requirements = Array.from({length: 4}, (_, i) => ({
    requirementId: `row-${i}`, candidateCount: i === 3 ? 1 : 0, requirementIndex: i,
    type: "skill" as const, importance: "must_have" as const,
    originalText: `技能要求${i + 1}`, normalizedCapability: null, eligibilityStatus: "conditional" as const,
    reason: i === 3 ? "只有实践，不能证明精通。" : "待核实。",
    evidenceIds: i === 3 ? ["synthetic-id"] : [], semanticVerdict: i === 3 ? "partial" as const : "not_matched" as const,
    profileFactRefs: [], assessmentSource: "provider" as const,
  }));
  const html = renderToStaticMarkup(React.createElement(MatchReportRequirementDetails, {requirements}));
  assert.match(html, /逐条判断（4 条）/);
  assert.match(html, /技能要求4/);
  assert.match(html, /部分支持/);
  assert.match(html, /只有实践，不能证明精通/);
  assert.match(html, /引用了 1 条已确认经历/);
  assert.match(html, /没有引用已确认经历/);
});

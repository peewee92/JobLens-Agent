import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import {renderToStaticMarkup} from "react-dom/server";
import {SavedMatchReportNotice} from "../components/saved-match-report-notice";
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

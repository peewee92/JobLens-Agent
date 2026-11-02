import assert from "node:assert/strict";
import test from "node:test";
import {readFileSync} from "node:fs";
import React from "react";
import {renderToStaticMarkup} from "react-dom/server";
import {rankedReportSnapshot} from "../lib/ranked-report";
import {SavedRankedJobExplanation} from "../components/ranked-job-explanation";
import type {JobMatchReport, MatchReportHistoryItem} from "../lib/contracts";

const report = JSON.parse(readFileSync(new URL("../../../packages/contracts/examples/match-report.example.json", import.meta.url), "utf8")) as JobMatchReport;
function saved(id: string, current: boolean): MatchReportHistoryItem {
  return {reportId:id, report:{...report, jobId:"job-original"}, createdAt:"2026-10-30T00:00:00Z", isCurrent:current,
    staleReasons:current ? [] : ["profile_changed"]};
}

test("ranking reads its exact historical report instead of the latest", () => {
  const old = saved("bound-old", false), latest = saved("latest", true);
  const history = {items:[latest, old], count:2};
  assert.equal(rankedReportSnapshot(history, "job-original", "bound-old"), old);
  assert.equal(rankedReportSnapshot(history, "job-original", "missing"), null);
  assert.equal(rankedReportSnapshot(history, "other-job", "bound-old"), null);
});

test("decision summary exposes the saved recommendation, reasons and historical warning", () => {
  const html = renderToStaticMarkup(React.createElement(SavedRankedJobExplanation, {saved:saved("old", false), position:1}));
  assert.match(html, /第 1 项/);
  assert.match(html, /当前事实已变化/);
  assert.match(html, /排序位置不是录用概率/);
  assert.ok(html.includes(report.summary));
  for (const item of report.risks.slice(0, 2)) assert.ok(html.includes(item.reason));
});

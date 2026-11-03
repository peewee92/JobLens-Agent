import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import {renderToStaticMarkup} from "react-dom/server";
import {JobDescriptionObservationsView} from "../components/job-description-observations";

test("history shows saved descriptions and uncertainty without claiming restoration", () => {
  const history = {jobId: "j", hasMore: true, items: [
    {importId: "i", inputIndex: 1, recordedAt: "2026-10-29T12:00:00Z", description: "完整历史描述", truncated: false},
    {importId: "i", inputIndex: 0, recordedAt: "2026-10-29T12:00:00Z", description: null, truncated: false},
  ]};
  const html = renderToStaticMarkup(React.createElement(JobDescriptionObservationsView, {history}));
  for (const text of ["完整历史描述", "无法还原原文", "更早的记录未显示", "不会恢复或重新分析"]) assert.ok(html.includes(text));
  assert.doesNotMatch(html, /<button/);
});

test("failed history read is distinct from empty history", () => {
  const failed = renderToStaticMarkup(React.createElement(JobDescriptionObservationsView, {history: null}));
  const empty = renderToStaticMarkup(React.createElement(JobDescriptionObservationsView, {history: {jobId: "j", hasMore: false, items: []}}));
  assert.match(failed, /暂时无法读取/);
  assert.match(empty, /没有可查看的导入观察记录/);
});

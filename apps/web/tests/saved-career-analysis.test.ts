import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import {renderToStaticMarkup} from "react-dom/server";
import example from "../../../packages/contracts/examples/career-agent-analysis-result.example.json";
import type {SavedCareerAnalysis} from "../lib/contracts";
import {SavedCareerAnalysisView} from "../components/saved-career-analysis-view";

const result = example as SavedCareerAnalysis;

test("saved analysis renders the shared nonempty workflow result with exact evidence and report links", () => {
  const html = renderToStaticMarkup(React.createElement(SavedCareerAnalysisView, {result, backHref: "/agent?threadId=thread_example"}));
  assert.match(html, /本次目标岗位的差距与准备材料/);
  assert.match(html, /不会在打开时重新生成/);
  assert.match(html, /reportId=report_1/);
  assert.match(html, /extract_1/);
  assert.match(html, /Python/);
  assert.match(html, /req_python/);
  assert.match(html, /ev_react/);
  assert.match(html, /建议行动与完成标准/);
  assert.match(html, /已有技能记录，证据待补充/);
  assert.doesNotMatch(html, /按当前资料查看能力差距/);
});

test("changed facts show the same historical materials, never a silently refreshed version", () => {
  const historical = {...result, isCurrent: false, staleReasons: ["profile_changed"]};
  const html = renderToStaticMarkup(React.createElement(SavedCareerAnalysisView, {result: historical, backHref: "/agent"}));
  assert.match(html, /历史材料：当前事实已变化/);
  assert.match(html, /不要将它当作当前建议/);
  assert.match(html, /ev_react/);
  assert.match(html, /profile_changed/); // Reason code is in the explicit technical disclosure.
  assert.doesNotMatch(html, /事实版本仍适用于当前资料/);
});

import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import {renderToStaticMarkup} from "react-dom/server";
import {ImportAnalysisScopes} from "../components/import-analysis-scopes";

const render = (jobIds: string[]) => renderToStaticMarkup(React.createElement(ImportAnalysisScopes, {jobIds}));
test("persisted results remain available in bounded scopes", () => {
  const html = render(Array.from({length: 51}, (_, i) => `job_${i}`));
  assert.match(html, /当前有 51 个岗位已保存匹配/);
  assert.match(html, /选择第 1 组的 50 个岗位进行分析/);
  assert.match(html, /选择第 2 组的 1 个岗位进行分析/);
  assert.equal((html.match(/scopeJobId=/g) ?? []).length, 51);
  assert.match(html, /scopeJobId=job_50/);
});
test("empty and duplicate results do not invent scopes", () => {
  assert.equal(render([]), "");
  assert.equal((render(["job_a", "job_a"]).match(/scopeJobId=/g) ?? []).length, 1);
});

import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import {renderToStaticMarkup} from "react-dom/server";
import {AnalysisExecutionControls} from "../components/analysis-execution-controls";

const render = (isUpdate: boolean, isCurrent = true) => renderToStaticMarkup(React.createElement(AnalysisExecutionControls, {
  threadId: "thread", resultId: "result", jobIds: ["job"], isCurrent, isUpdate,
}));

test("update results explain explicit application and preservation of history", () => {
  const html = render(true);
  assert.match(html, /保存新分析不会自动更改工作区/);
  assert.match(html, /已有投递状态、历史材料和行动进度会保留/);
  assert.match(html, /应用新分析到工作区（1 个岗位）/);
  assert.match(html, /不会调用模型或自动投递/);
});

test("initial and stale results retain their distinct actions", () => {
  assert.match(render(false), /开始执行（1 个岗位）/);
  assert.doesNotMatch(render(false), /保存新分析不会自动更改工作区/);
  const stale = render(true, false);
  assert.match(stale, /这份分析已过期/);
  assert.match(stale, /disabled=""/);
});

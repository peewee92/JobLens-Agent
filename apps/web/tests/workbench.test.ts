import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import {renderToStaticMarkup} from "react-dom/server";
import {WorkbenchView} from "../components/workbench-view";
import {type Workbench, workbenchChangeLabel, inputIssueLabel} from "../lib/workbench";

const empty: Workbench = {snapshot: {profileVersion: null, searchIntentVersion: null, evidenceCount: 0,
  inputIssueCodes: ["profile_missing", "search_intent_missing"], jobCount: 0, currentRun: null,
  workspaces: [], changes: []}, nextAction: {code: "confirm_inputs", label: "确认我的资料和意向", reason: "只用已确认事实", href: "/profile"}};

test("workbench renders four real task areas and one primary action, including browse when facts missing", () => {
  const html = renderToStaticMarkup(React.createElement(WorkbenchView, {data: empty}));
  for (const name of ["当前准备情况", "当前分析", "目标岗位与执行", "最近变化", "尚未确认职业资料", "尚未确认求职意向"]) assert.ok(html.includes(name));
  assert.equal((html.match(/class="button"/g) ?? []).length, 1);
  assert.ok(html.includes('href="/jobs"'));
  assert.match(html, /不会启动分析或调用模型/);
  assert.doesNotMatch(html, /匹配概率|已满足全部/);
});

test("workbench uses canonical historical analysis and workspace links, never a live gap page as old result", () => {
  const data: Workbench = {...empty, snapshot: {...empty.snapshot, profileVersion: 2, searchIntentVersion: 1, inputIssueCodes: [],
    currentRun: {threadId: "run a", resultId: "saved1", resultIsCurrent: false, status: "completed", currentStep: "done",
      jobCount: 2, targetCount: 2, executionTargetCount: 1, updatedAt: "2026-10-25T00:00:00Z"},
    workspaces: [{workspaceId: "w1", jobId: "j1", title: "真实目标岗位", status: "applied", openActionCount: 1, currentAnalysisThreadId: "run a"}],
    changes: [{kind: "action_completed", occurredAt: "2026-10-25T01:00:00Z", href: "/applications/w1"}]}};
  const html = renderToStaticMarkup(React.createElement(WorkbenchView, {data}));
  assert.match(html, /事实已变化/);
  assert.match(html, /href="\/agent\/results\/run%20a"/);
  assert.match(html, /href="\/applications\/w1"/);
  assert.match(html, /已投递/);
  assert.match(html, /完成了一项准备行动/);
  assert.doesNotMatch(html, /href="\/gaps/);
});

test("workbench does not pretend an old completion without stored materials is a saved result", () => {
  const data: Workbench = {...empty, snapshot: {...empty.snapshot, currentRun: {
    threadId: "legacy", status: "completed", currentStep: "done", jobCount: 2, targetCount: 2,
    executionTargetCount: 0, resultId: null, resultIsCurrent: null, updatedAt: "2026-10-25T00:00:00Z"}}};
  const html = renderToStaticMarkup(React.createElement(WorkbenchView, {data}));
  assert.match(html, /历史运行没有保存完整材料/);
  assert.doesNotMatch(html, /打开本次保存的完整分析/);
  assert.equal(workbenchChangeLabel("analysis_interrupted"), "分析状态：等待确认目标");
  assert.equal(inputIssueLabel("profile_skill_evidence_missing"), "部分技能尚未关联已确认经历");
});

test('saved analyses and linked workspaces share scoped update entry, legacy completions have no fabricated update', () => {
  const data: Workbench = {...empty,snapshot:{...empty.snapshot,currentRun:{threadId:'saved run',resultId:'result',resultIsCurrent:false,status:'completed',currentStep:'done',jobCount:2,targetCount:2,executionTargetCount:2,updatedAt:'2026-10-27'},
    workspaces:[{workspaceId:'w',jobId:'j',title:'目标',status:'preparing',openActionCount:2,currentAnalysisThreadId:'source run'}]}};
  const html=renderToStaticMarkup(React.createElement(WorkbenchView,{data}));
  assert.ok(html.includes('/agent/results/saved%20run/update'));assert.ok(html.includes('/agent/results/source%20run/update'));
  assert.doesNotMatch(html,/rematch/);
});

test('partial completion never reads as all requested jobs analysed',()=>{
  const data:Workbench={...empty,snapshot:{...empty.snapshot,currentRun:{threadId:'partial',resultId:'r',resultIsCurrent:true,status:'completed',currentStep:'done',jobCount:8,targetCount:3,executionTargetCount:3,updatedAt:'2026-10-27',partial:true,completedReportCount:5}}};
  const html=renderToStaticMarkup(React.createElement(WorkbenchView,{data}));
  for(const text of ['部分范围已保存','只完成或复用了 5 个岗位','不代表已淘汰']) assert.ok(html.includes(text),text);
  assert.equal(workbenchChangeLabel('analysis_partial'),'保存了部分范围分析');
});

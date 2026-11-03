import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import {renderToStaticMarkup} from "react-dom/server";
import {AnalysisUpdatePlanView} from "../components/analysis-update-plan-view";
import type {AnalysisUpdatePlan} from "../lib/contracts";

const base: AnalysisUpdatePlan = {sourceThreadId: "original a", sourceResultId: "saved", scope: "targets",
  inputDigest: "a".repeat(64), previousProfileVersion: 1, profileId: "p2", profileVersion: 2, searchIntentId: "s", searchIntentVersion: 1,
  maxNewAnalyses: 5, items: [], nextJobIds: [], reusableJobIds: [], advisoryOnly: true};

test("scope selection is a GET, not another analysis or an implicit paid command", () => {
  const html = renderToStaticMarkup(React.createElement(AnalysisUpdatePlanView, {plan: base}));
  assert.match(html, /method="GET"/);
  assert.match(html, /original%20a\/update/);
  assert.match(html, /原确认目标岗位/); assert.match(html, /原分析整批岗位/);
  assert.match(html, /当前仅预检，没有重算、保存新结果或调用模型/);
  assert.match(html, /每次最多新增分析 5 个岗位/);
  assert.doesNotMatch(html, /method="POST"|更新已完成|已授权模型/);
});

test("real statuses and repair links distinguish missing inputs, paid requirements and rule candidates", () => {
  const plan: AnalysisUpdatePlan = {...base, nextJobIds: ["ready"], reusableJobIds: ["reuse"], items:
    (["reuse", "ready", "deferred", "requires_model", "input_blocked"] as const).map((status, index) => ({
      inputFingerprint: "fixed", baseReportId: null, jobId: status, title: `真实岗位${index}`, status, extractionId: status === "input_blocked" ? null : "ex1",
      reusableReportId: status === "reuse" ? "report" : null, staleReasons: ["profile_changed"],
      blockerCodes: status === "requires_model" ? ["model_authorization_required"] : status === "input_blocked" ? ["requirements_missing"] : [],
      requiredOperations: status === "requires_model" ? ["semantic_match"] : [], repairHref: "/jobs/example",
    }))};
  const html = renderToStaticMarkup(React.createElement(AnalysisUpdatePlanView, {plan}));
  for (const label of ["可复用当前报告", "可由规则重算（尚未执行）", "留待下一小批", "需要单独授权模型", "先修复输入", "职业资料已更新"]) assert.ok(html.includes(label));
  assert.match(html, /href="\/jobs\/example"/);
  assert.match(html, /未授权时停在这里，不自动调用或切换模型/);
});

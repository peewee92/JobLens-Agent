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
  assert.doesNotMatch(html, /这些材料仍适用于当前资料/);
});

test("saved gap guidance translates known internal codes and folds evidence identifiers", () => {
  const html = renderToStaticMarkup(React.createElement(SavedCareerAnalysisView, {result, backHref: "/agent"}));
  assert.doesNotMatch(html, />capability_missing</);
  assert.doesNotMatch(html, />confirmed_profile_skill_exists</);
  assert.match(html, /查看来源证据/);
});

test("saved comparison uses its actual scope, shows real names and calls a bonus optional", () => {
  const seeded = {...result, unrankedJobIds: ["j-hard", "j-short"], gaps: {...result.gaps,
    items: [{...result.gaps.items[0], capability: "Docker", priority: "P0",
      whyImportant: {mustHaveRatio: 0}, supportingRequirementIds: ["bonus-docker"]}]},
    preparations: result.preparations.map(p => ({...p, studyChecklist: {items: [{
      requirementId: "bonus-docker", requirementText: "加分项：熟悉 Docker 部署",
      capability: "Docker", importance: "bonus", evidenceStatus: "missing", need: "optional",
      profileSkillIds: [], completionCriteria: [],
    }]}}))};
  const html = renderToStaticMarkup(React.createElement(SavedCareerAnalysisView, {
    result: seeded, backHref: "/agent", additionalLabels: {"j-hard": "硬件验证工程师"},
    savedScope: {requested: ["job_1", "j-hard", "j-short"], compared: 1},
    currentOmissions: [{jobId: "j-hard", reason: "hard_conflict", staleReasons: []}],
  }));
  assert.match(html, /已选 3 个岗位，实际比较 1 个/);
  assert.match(html, /硬件验证工程师<\/a>：当前匹配发现明确/);
  assert.match(html, /名称暂不可读取的岗位<\/a>/);
  assert.match(html, /来自当前检查/);
  assert.match(html, /加分项 · 可选补充/);
  assert.doesNotMatch(html, /P0 · Docker/);
  assert.match(html, /#saved-resume-0/);
  assert.match(html, /#saved-interview-0/);
});

test("interview can refer to a saved match without rewriting the preparation facts", () => {
  const jobId = result.preparations[0].jobId;
  const html = renderToStaticMarkup(React.createElement(SavedCareerAnalysisView, {
    result, backHref: "/agent", savedMatchedSupport: {[jobId]: ["req_python"]},
  }));
  assert.match(html, /当时的匹配找到了已确认经历，这份面试材料没有直接引用/);
  assert.match(html, /reportId=report_1#job-match-report/);
  assert.match(html, /参见当时的匹配依据/);
});

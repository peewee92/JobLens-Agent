import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import {renderToStaticMarkup} from "react-dom/server";
import {JobReportComparison} from "../components/job-report-comparison";
import type {JobMatchReport, MatchReportHistoryItem, MatchReportRequirementResult} from "../lib/contracts";

const requirement: MatchReportRequirementResult = {requirementId:"r1", requirementIndex:0, type:"skill", importance:"must_have", originalText:"Python 后端", normalizedCapability:"Python", eligibilityStatus:"conditional", semanticVerdict:"not_matched", evidenceIds:[], profileFactRefs:[], reason:"没有检索到证据", candidateCount:1, assessmentSource:"provider"};
const report: JobMatchReport = {jobId:"j1", profileId:"p1", profileVersion:1, extractionId:"e1", searchIntentId:"s1", searchIntentVersion:1, eligibility:"conditional", recommendation:"low", summary:"", strengths:[], risks:[], requirementResults:[requirement], matchedRequirementIds:[], partialRequirementIds:[], missingRequirementIds:[], evidenceLinks:[], retrievalVersion:"evidence-retrieval-v2", policyVersion:"v1", matcherVersion:"m1", promptVersion:"p1", model:null, traceRunId:null, dbWrites:1, providerCalls:0, traceRunsCreated:0};
const wrap = (value: JobMatchReport, id: string): MatchReportHistoryItem => ({reportId:id, createdAt:"2026-01-01T00:00:00Z", isCurrent:id === "new", staleReasons:[], report:value});
const render = (oldReport: JobMatchReport, newReport: JobMatchReport) => renderToStaticMarkup(React.createElement(JobReportComparison,{previous:wrap(oldReport,"old"), current:wrap(newReport,"new")}));
test("saved requirements show real changes without attributing cause", () => {
  const updated: JobMatchReport = {...report, profileVersion:2, recommendation:"strong", requirementResults:[{...requirement, semanticVerdict:"matched", reason:"有真实证据"}]};
  const html = render(report, updated);
  assert.match(html, /证据未覆盖 → 已有支持/); assert.match(html, /没有检索到证据/); assert.match(html, /有真实证据/); assert.match(html, /不推断变化原因/);
});
test("unchanged verdict does not promise improvement", () => {
  const html = render(report, {...report, profileVersion:2});
  assert.match(html, /逐项判断、原因和证据引用没有变化/);
});
test("incompatible versions and unrecorded policy cannot imply comparable findings", () => {
  for (const changed of [{extractionId:"e2"}, {policyVersion:undefined}, {policyVersion:"v2"}, {retrievalVersion:undefined}, {retrievalVersion:"other"}]) {
    const html = render(report, {...report, ...changed});
    assert.match(html, /不能直接比较逐项判断/); assert.doesNotMatch(html, /逐项判断、原因和证据引用没有变化/);
  }
});
test("intent or matcher differences are explicitly disclosed", () => {
  const html = render(report, {...report, searchIntentVersion:2, model:"other"});
  assert.match(html, /求职意向不同/); assert.match(html, /匹配方法或模型记录不同/);
});
test("different jobs are never compared", () => assert.equal(render(report, {...report, jobId:"j2"}), ""));

test("missing details or intent metadata never imply equality", () => {
  const empty = {...report, requirementResults:[], searchIntentId:undefined};
  const html = render(empty, empty);
  assert.match(html, /没有可比较的要求明细/);
  assert.match(html, /未记录完整的求职意向版本/);
  assert.doesNotMatch(html, /逐项判断、原因和证据引用没有变化/);
});

test("changed evidence or explanation is visible even when verdict stays the same", () => {
  const html = render(report, {...report, requirementResults:[{...requirement, reason:"新解释", evidenceIds:["ev1"]}]});
  assert.match(html, /证据未覆盖 → 证据未覆盖/);
  assert.match(html, /证据 0 条 → 1 条/);
  assert.match(html, /新解释/);
});


test("no recalled candidates are pending, not a model rejection", () => {
  const before = {...report, requirementResults:[{...requirement, candidateCount:0, assessmentSource:"deterministic" as const}]};
  assert.match(render(before, report), /待核实 → 证据未覆盖/);
});

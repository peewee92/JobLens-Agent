import assert from "node:assert/strict";
import test from "node:test";
import {createElement} from "react";
import {renderToStaticMarkup} from "react-dom/server";
import {JobRequirementReviewList} from "../components/job-requirement-review-list";
import {FirstUseSteps} from "../components/first-use-steps";
import type {JobRequirement} from "../lib/contracts";

function row(id: string, values: Partial<JobRequirement> = {}): JobRequirement {
  return {
    id, jobId: "job_1", extractionId: "extract_1", type: "constraint",
    importance: "must_have", requirementIndex: 0, originalText: id, evidenceSpan: id,
    normalizedCapability: null, confidence: 0.9, extractorVersion: "test",
    ...values,
  };
}

test("show qualifications before duties and do not label a duty as an application requirement", () => {
  const html = renderToStaticMarkup(createElement(JobRequirementReviewList, {requirements: [
    row("Build transformations", {type: "responsibility", requirementIndex: 0}),
    row("Tableau", {type: "skill", importance: "preferred", requirementIndex: 1}),
    row("hold US work authorization", {requirementIndex: 2,
      evidenceSpan: "Candidates must live in the United States and hold US work authorization."}),
  ]}));
  assert.match(html, /申请条件与加分项.*必须.*hold US work authorization.*优先.*Tableau.*入职后要做的事.*Build transformations/);
  assert.doesNotMatch(html.split("入职后要做的事")[1], /必须|优先|加分/);
  assert.match(html, /<details[^>]*><summary>查看岗位原文依据<\/summary><blockquote>Candidates must live/);
  assert.doesNotMatch(html, /<details[^>]+open/);
  assert.equal(html.match(/Build transformations/g)?.length, 1);
  assert.match(html, /已显示完整的岗位原文依据/);
});

test("import step does not imply that job requirements have been reviewed", () => {
  const html = renderToStaticMarkup(createElement(FirstUseSteps, {snapshot: {
    profileVersion: null, searchIntentVersion: null, evidenceCount: 0,
    inputIssueCodes: ["profile_missing"], jobCount: 4, currentRun: null, workspaces: [], changes: [],
  }}));
  assert.match(html, /添加岗位<\/strong><small>已完成<\/small><\/div><p>先粘贴招聘描述；比较前，在对应岗位核对要求。/);
});

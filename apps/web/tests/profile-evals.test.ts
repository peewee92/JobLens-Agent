import assert from "node:assert/strict";
import test from "node:test";

import type {ProfileEvalCaseResult, ProfileEvalRunSummary} from "../lib/contracts";
import {
  formatDelta,
  formatRate,
  reviewActionsForRun,
  sortProfileEvalCases,
} from "../lib/profile-evals";

function run(overrides: Partial<ProfileEvalRunSummary> = {}): ProfileEvalRunSummary {
  return {
    id: "eval_1",
    datasetVersion: "profile-extraction-v1",
    mode: "live",
    provider: "openai",
    model: "configured-model",
    extractorVersion: "profile-extractor-v1",
    promptVersion: "profile-proposal-v1",
    gateVersion: "profile-eval-gate-v1",
    baselineRunId: null,
    totalCases: 10,
    passedCases: 10,
    casePassRate: 1,
    workflowSuccessRate: 1,
    skillRecall: 1,
    yearsAccuracy: 1,
    forbiddenFactRate: 0,
    gatePassed: true,
    releaseEligible: true,
    createdAt: "2026-08-03T00:00:00Z",
    ...overrides,
  };
}

function evalCase(caseId: string, passed: boolean): ProfileEvalCaseResult {
  return {
    caseId,
    traceRunId: `run_${caseId}`,
    workflowSucceeded: true,
    passed,
    failureCodes: passed ? [] : ["missing_expected_skill"],
    failureReasons: passed ? [] : ["missing expected skill"],
    expectedSkills: ["Agent"],
    actualSkills: passed ? ["Agent"] : [],
    missingSkills: passed ? [] : ["Agent"],
    expectedYears: 3,
    actualYears: 3,
    forbiddenTerms: [],
    observedForbiddenTerms: [],
    diagnostics: {},
  };
}

test("fixture runs cannot be formally reviewed", () => {
  const actions = reviewActionsForRun(run({mode: "fixture", releaseEligible: false}), false);
  assert.equal(actions.canAccept, false);
  assert.equal(actions.canReject, false);
  assert.match(actions.reason ?? "", /Fixture/);
});

test("failed live runs can be rejected but not accepted", () => {
  const actions = reviewActionsForRun(
    run({gatePassed: false, releaseEligible: false}),
    false,
  );
  assert.equal(actions.canAccept, false);
  assert.equal(actions.canReject, true);
});

test("eligible live runs can be accepted or rejected until reviewed", () => {
  assert.deepEqual(reviewActionsForRun(run(), false), {
    canAccept: true,
    canReject: true,
    reason: null,
  });
  const reviewed = reviewActionsForRun(run(), true);
  assert.equal(reviewed.canAccept, false);
  assert.equal(reviewed.canReject, false);
});

test("failed cases sort before passed cases without mutating input", () => {
  const input = [evalCase("passed", true), evalCase("failed", false)];
  const sorted = sortProfileEvalCases(input);
  assert.deepEqual(sorted.map((item) => item.caseId), ["failed", "passed"]);
  assert.deepEqual(input.map((item) => item.caseId), ["passed", "failed"]);
});

test("rate and delta formatting preserve sign and null", () => {
  assert.equal(formatRate(0.955), "95.5%");
  assert.equal(formatRate(null), "—");
  assert.equal(formatDelta(0.02), "+2.0%");
  assert.equal(formatDelta(-0.01), "-1.0%");
});

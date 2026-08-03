import assert from "node:assert/strict";
import test from "node:test";

import type {
  RequirementEvalCaseResult,
  RequirementEvalRunSummary,
} from "../lib/contracts";
import {
  formatDelta,
  formatRate,
  reviewActionsForRequirementRun,
  sortRequirementEvalCases,
} from "../lib/requirement-evals";

function run(
  overrides: Partial<RequirementEvalRunSummary> = {},
): RequirementEvalRunSummary {
  return {
    id: "reqeval_1",
    datasetVersion: "requirement-extraction-v1",
    mode: "live",
    provider: "openai",
    model: "configured-model",
    extractorVersion: "requirement-extractor-v1",
    promptVersion: "requirement-extraction-v1",
    gateVersion: "requirement-eval-gate-v1",
    baselineRunId: null,
    totalCases: 10,
    passedCases: 10,
    casePassRate: 1,
    workflowSuccessRate: 1,
    capabilityRecall: 1,
    importanceAccuracy: 1,
    forbiddenCapabilityRate: 0,
    gatePassed: true,
    releaseEligible: true,
    createdAt: "2026-08-03T00:00:00Z",
    ...overrides,
  };
}

function evalCase(
  caseId: string,
  passed: boolean,
): RequirementEvalCaseResult {
  return {
    caseId,
    traceRunId: `run_${caseId}`,
    workflowSucceeded: true,
    passed,
    missingRequirements: passed ? [] : ["skill:Python:must_have"],
    wrongImportance: [],
    observedForbiddenCapabilities: [],
    actualRequirements: passed ? ["skill:Python:must_have"] : [],
    error: null,
  };
}

test("fixture Requirement runs cannot be formally reviewed", () => {
  const actions = reviewActionsForRequirementRun(
    run({mode: "fixture", releaseEligible: false}),
    false,
  );
  assert.equal(actions.canAccept, false);
  assert.equal(actions.canReject, false);
  assert.match(actions.reason ?? "", /Fixture/);
});

test("failed live Requirement runs can be rejected but not accepted", () => {
  const actions = reviewActionsForRequirementRun(
    run({gatePassed: false, releaseEligible: false}),
    false,
  );
  assert.equal(actions.canAccept, false);
  assert.equal(actions.canReject, true);
});

test("eligible live Requirement runs can be accepted or rejected until reviewed", () => {
  assert.deepEqual(reviewActionsForRequirementRun(run(), false), {
    canAccept: true,
    canReject: true,
    reason: null,
  });
  const reviewed = reviewActionsForRequirementRun(run(), true);
  assert.equal(reviewed.canAccept, false);
  assert.equal(reviewed.canReject, false);
});

test("failed Requirement cases sort before passed cases without mutation", () => {
  const input = [evalCase("passed", true), evalCase("failed", false)];
  const sorted = sortRequirementEvalCases(input);
  assert.deepEqual(sorted.map((item) => item.caseId), ["failed", "passed"]);
  assert.deepEqual(input.map((item) => item.caseId), ["passed", "failed"]);
});

test("Requirement rate and delta formatting preserve sign and null", () => {
  assert.equal(formatRate(0.955), "95.5%");
  assert.equal(formatRate(null), "—");
  assert.equal(formatDelta(0.02), "+2.0%");
  assert.equal(formatDelta(-0.01), "-1.0%");
});

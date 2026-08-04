import assert from "node:assert/strict";
import test from "node:test";

import type {
  RequirementAcceptanceRunCase,
  RequirementAcceptanceRunSummary,
} from "../lib/contracts";
import {
  attemptedCanaryCases,
  requirementAcceptanceCaseStatusLabels,
  requirementAcceptanceDatasetStateLabels,
  requirementAcceptanceNextActionClass,
  requirementAcceptanceNextActionLabels,
  requirementAcceptanceRunStatusLabels,
  sortRequirementAcceptanceRuns,
} from "../lib/requirement-acceptance-runs";

function runSummary(
  id: string,
  overrides: Partial<RequirementAcceptanceRunSummary> = {},
): RequirementAcceptanceRunSummary {
  return {
    id,
    title: `Run ${id}`,
    reviewer: "will",
    provider: "openai",
    model: "quality-model",
    extractorVersion: "requirement-extractor-v1",
    promptVersion: "requirement-extraction-v1",
    status: "partial",
    attemptedCalls: 2,
    completedCaseCount: 2,
    failedCount: 0,
    deferredCount: 18,
    canaryReviewRequired: false,
    canaryDecision: null,
    batchId: null,
    createdAt: "2026-08-04T10:00:00Z",
    updatedAt: "2026-08-04T10:00:00Z",
    ...overrides,
  };
}

function runCase(
  caseIndex: number,
  overrides: Partial<RequirementAcceptanceRunCase> = {},
): RequirementAcceptanceRunCase {
  return {
    id: `case_${caseIndex}`,
    caseIndex,
    sourceUrl: `https://example.com/${caseIndex}`,
    title: `Job ${caseIndex}`,
    company: "Example",
    descriptionHash: "hash",
    descriptionSnapshot: "Frozen JD",
    currentDescriptionHash: "hash",
    descriptionIsCurrent: true,
    isCanaryEvidence: false,
    jobId: `job_${caseIndex}`,
    status: "deferred",
    attemptCount: 0,
    extractionId: null,
    traceRunId: null,
    traceCapability: null,
    traceModel: null,
    tracePromptVersion: null,
    traceLatencyMs: null,
    traceInputTokens: null,
    traceOutputTokens: null,
    traceError: null,
    traceCreatedAt: null,
    errorCode: null,
    errorMessage: null,
    createdAt: "2026-08-04T10:00:00Z",
    updatedAt: "2026-08-04T10:00:00Z",
    ...overrides,
  };
}

test("readiness labels keep blockers execution and human review distinct", () => {
  assert.equal(
    requirementAcceptanceDatasetStateLabels.selection_required,
    "存在多个正式数据集，需明确选择",
  );
  assert.equal(
    requirementAcceptanceNextActionLabels.fix_blockers,
    "先修复准备阻塞",
  );
  assert.equal(
    requirementAcceptanceNextActionLabels.review_canary,
    "需要你人工审核 Canary",
  );
  assert.equal(requirementAcceptanceNextActionClass("run_canary"), "status-pass");
  assert.equal(requirementAcceptanceNextActionClass("review_canary"), "status-live");
  assert.equal(requirementAcceptanceNextActionClass("stopped"), "status-fail");
});

test("runs awaiting human review sort before completed history", () => {
  const ready = runSummary("ready", {status: "ready"});
  const partial = runSummary("partial", {status: "partial"});
  const awaiting = runSummary("awaiting", {status: "awaiting_canary_review"});
  const input = [ready, partial, awaiting];
  const sorted = sortRequirementAcceptanceRuns(input);
  assert.deepEqual(sorted.map((item) => item.id), ["awaiting", "partial", "ready"]);
  assert.deepEqual(input.map((item) => item.id), ["ready", "partial", "awaiting"]);
});

test("Canary evidence includes only actually attempted cases in source order", () => {
  const deferred = runCase(0);
  const secondAttempted = runCase(2, {
    status: "failed",
    attemptCount: 1,
    isCanaryEvidence: true,
    traceRunId: "trace_2",
  });
  const firstAttempted = runCase(1, {
    status: "extracted",
    attemptCount: 1,
    isCanaryEvidence: true,
    extractionId: "reqrun_1",
    traceRunId: "trace_1",
  });
  assert.deepEqual(
    attemptedCanaryCases([secondAttempted, deferred, firstAttempted]).map(
      (item) => item.caseIndex,
    ),
    [1, 2],
  );
});

test("status labels keep failed deferred and awaiting semantics distinct", () => {
  assert.equal(requirementAcceptanceCaseStatusLabels.failed, "调用失败");
  assert.equal(requirementAcceptanceCaseStatusLabels.deferred, "本轮未调用");
  assert.equal(
    requirementAcceptanceRunStatusLabels.awaiting_canary_review,
    "等待 Canary 人工判断",
  );
});

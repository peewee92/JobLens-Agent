import assert from "node:assert/strict";
import test from "node:test";

import type {
  RequirementReviewBatchCase,
  RequirementReviewBatchSummary,
  RequirementReviewCandidate,
} from "../lib/contracts";
import {
  canSelectRequirementCandidate,
  requirementReviewCohortKey,
  requirementReviewEvidenceLabel,
  sortRequirementReviewCases,
} from "../lib/requirement-reviews";

function candidate(
  extractionId: string,
  overrides: Partial<RequirementReviewCandidate> = {},
): RequirementReviewCandidate {
  return {
    extractionId,
    jobId: `job_${extractionId}`,
    title: "Agent Engineer",
    company: "Example",
    provider: "openai",
    model: "quality-model",
    extractorVersion: "requirement-extractor-v1",
    promptVersion: "requirement-extraction-v1",
    traceRunId: `run_${extractionId}`,
    requirementCount: 3,
    createdAt: "2026-08-03T00:00:00Z",
    ...overrides,
  };
}

function summary(
  overrides: Partial<RequirementReviewBatchSummary> = {},
): RequirementReviewBatchSummary {
  return {
    id: "reqreviewbatch_1",
    title: "Manual quality review",
    reviewer: "will",
    provider: "openai",
    model: "quality-model",
    extractorVersion: "requirement-extractor-v1",
    promptVersion: "requirement-extraction-v1",
    sampleSize: 20,
    reviewedCount: 20,
    acceptedCount: 18,
    rejectedCount: 2,
    staleCaseCount: 0,
    completed: true,
    formalEvidenceEligible: true,
    createdAt: "2026-08-03T00:00:00Z",
    ...overrides,
  };
}

function reviewCase(
  caseIndex: number,
  overrides: Partial<RequirementReviewBatchCase> = {},
): RequirementReviewBatchCase {
  return {
    id: `case_${caseIndex}`,
    caseIndex,
    jobId: `job_${caseIndex}`,
    extractionId: `reqrun_${caseIndex}`,
    title: `Job ${caseIndex}`,
    company: "Example",
    description: "JD",
    provider: "openai",
    model: "quality-model",
    extractorVersion: "requirement-extractor-v1",
    promptVersion: "requirement-extraction-v1",
    traceRunId: `run_${caseIndex}`,
    createdAt: "2026-08-03T00:00:00Z",
    isCurrent: true,
    requirements: [],
    review: null,
    ...overrides,
  };
}

test("cohort key includes provider model extractor and prompt", () => {
  assert.equal(
    requirementReviewCohortKey(candidate("one")),
    "openai::quality-model::requirement-extractor-v1::requirement-extraction-v1",
  );
});

test("selection allows only one cohort and at most twenty", () => {
  const first = candidate("one");
  const same = candidate("two");
  const mixed = candidate("three", {model: "other-model"});
  assert.equal(canSelectRequirementCandidate(first, []), true);
  assert.equal(canSelectRequirementCandidate(same, [first]), true);
  assert.equal(canSelectRequirementCandidate(mixed, [first]), false);
  const twenty = Array.from({length: 20}, (_, index) => candidate(`selected-${index}`));
  assert.equal(canSelectRequirementCandidate(candidate("extra"), twenty), false);
  assert.equal(canSelectRequirementCandidate(twenty[0], twenty), true);
});

test("pending and stale cases sort before completed current cases", () => {
  const reviewedCurrent = reviewCase(0, {
    review: {
      id: "review_0",
      batchCaseId: "case_0",
      decision: "accepted",
      issueCodes: [],
      notes: "reviewed",
      reviewedAt: "2026-08-03T00:00:00Z",
    },
  });
  const pendingCurrent = reviewCase(1);
  const pendingStale = reviewCase(2, {isCurrent: false});
  const input = [reviewedCurrent, pendingCurrent, pendingStale];
  const sorted = sortRequirementReviewCases(input);
  assert.deepEqual(sorted.map((item) => item.id), ["case_2", "case_1", "case_0"]);
  assert.deepEqual(input.map((item) => item.id), ["case_0", "case_1", "case_2"]);
});

test("evidence labels distinguish formal practice pending fixture and stale", () => {
  assert.equal(
    requirementReviewEvidenceLabel(summary()),
    "20 条正式人工质量证据",
  );
  assert.match(
    requirementReviewEvidenceLabel(summary({staleCaseCount: 1, formalEvidenceEligible: false})),
    /已过期/,
  );
  assert.match(
    requirementReviewEvidenceLabel(
      summary({reviewedCount: 3, completed: false, formalEvidenceEligible: false}),
    ),
    /进行中/,
  );
  assert.equal(
    requirementReviewEvidenceLabel(
      summary({provider: "fixture", formalEvidenceEligible: false}),
    ),
    "Fixture 练习证据",
  );
  assert.match(
    requirementReviewEvidenceLabel(
      summary({sampleSize: 5, reviewedCount: 5, formalEvidenceEligible: false}),
    ),
    /练习批次/,
  );
});

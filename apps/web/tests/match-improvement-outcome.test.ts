import assert from "node:assert/strict";
import test from "node:test";

import type {MatchImprovement} from "../lib/contracts";
import {
  classifyMatchImprovementOutcome,
  shouldDeferImmediateEvidenceRepeat,
} from "../lib/match-improvement-outcome";

function improvement(overrides: Partial<MatchImprovement> = {}): MatchImprovement {
  return {
    jobId: "job-1",
    currentReportId: "report-2",
    previousReportId: "report-1",
    previousRecommendation: "stretch",
    currentRecommendation: "stretch",
    previousProfileVersion: 1,
    currentProfileVersion: 2,
    previousMissingRequirementCount: 2,
    currentMissingRequirementCount: 2,
    resolvedRequirementIds: [],
    newlyMissingRequirementIds: [],
    resolvedRequirements: [],
    newlyMissingRequirements: [],
    newlySupportingEvidence: [],
    comparable: true,
    dbWrites: 0,
    providerCalls: 0,
    traceRunsCreated: 0,
    ...overrides,
  };
}

test("reports improved when a requirement is resolved", () => {
  assert.equal(
    classifyMatchImprovementOutcome(improvement({resolvedRequirementIds: ["req-1"]})),
    "improved",
  );
});

test("reports improved when recommendation changes", () => {
  assert.equal(
    classifyMatchImprovementOutcome(improvement({currentRecommendation: "good"})),
    "improved",
  );
});

test("reports unchanged only after a comparable profile-version change", () => {
  assert.equal(classifyMatchImprovementOutcome(improvement()), "unchanged");
});

test("verified unchanged focused requirement pauses immediate repeat", () => {
  assert.equal(shouldDeferImmediateEvidenceRepeat(improvement(), "req-focus", true), true);
  assert.equal(shouldDeferImmediateEvidenceRepeat(improvement(), "req-focus", false), false);
});

test("unverifiable history never becomes a repeat-suppression signal", () => {
  assert.equal(shouldDeferImmediateEvidenceRepeat(null, "req-focus", true), false);
  assert.equal(
    shouldDeferImmediateEvidenceRepeat(improvement({comparable: false}), "req-focus", true),
    false,
  );
});

test("does not turn missing or incomparable comparison evidence into no improvement", () => {
  assert.equal(classifyMatchImprovementOutcome(null), "unverifiable");
  assert.equal(
    classifyMatchImprovementOutcome(improvement({comparable: false})),
    "unverifiable",
  );
  assert.equal(
    classifyMatchImprovementOutcome(improvement({previousProfileVersion: 2, currentProfileVersion: 2})),
    "unverifiable",
  );
});

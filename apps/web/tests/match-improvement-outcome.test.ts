import assert from "node:assert/strict";
import test from "node:test";

import type {MatchImprovement} from "../lib/contracts";
import {
  classifyExpectedImpactOutcome,
  classifyMatchImprovementOutcome,
  diagnoseFocusedRequirementOutcome,
  listNewlySupportedRequirements,
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

test("expected impact distinguishes the targeted requirement from unrelated improvement", () => {
  assert.equal(
    classifyExpectedImpactOutcome(improvement({resolvedRequirementIds: ["req-target"]}), ["req-target", "req-other"]),
    "target_resolved",
  );
  assert.equal(
    classifyExpectedImpactOutcome(improvement({resolvedRequirementIds: ["req-unrelated"]}), ["req-target"]),
    "other_improved",
  );
  assert.equal(
    classifyExpectedImpactOutcome(improvement({currentRecommendation: "good"}), ["req-target"]),
    "other_improved",
  );
  assert.equal(classifyExpectedImpactOutcome(improvement(), ["req-target"]), "unchanged");
  assert.equal(classifyExpectedImpactOutcome(null, ["req-target"]), "unverifiable");
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

test("diagnoses focused requirement outcomes only from comparable requirement and evidence facts", () => {
  assert.equal(
    diagnoseFocusedRequirementOutcome(
      improvement({resolvedRequirementIds: ["req-focus"], currentMissingRequirementCount: 1}),
      "req-focus",
      false,
    ),
    "resolved_with_other_hard_gaps",
  );
  assert.equal(
    diagnoseFocusedRequirementOutcome(
      improvement({
        newlySupportingEvidence: [{
          evidenceId: "ev-1",
          evidenceType: "project",
          summary: "Built a production workflow",
          supportingRequirements: [{requirementId: "req-focus", originalText: "Production workflow experience"}],
        }],
      }),
      "req-focus",
      true,
    ),
    "evidence_reached_requirement_but_still_missing",
  );
  assert.equal(
    diagnoseFocusedRequirementOutcome(
      improvement({
        newlySupportingEvidence: [{
          evidenceId: "ev-2",
          evidenceType: "work",
          summary: "Led frontend delivery",
          supportingRequirements: [{requirementId: "req-other", originalText: "Frontend leadership"}],
        }],
      }),
      "req-focus",
      true,
    ),
    "evidence_added_elsewhere",
  );
  assert.equal(
    diagnoseFocusedRequirementOutcome(improvement(), "req-focus", true),
    "no_new_matching_evidence",
  );
});

test("lists the concrete other requirements reached by newly supporting evidence", () => {
  const result = listNewlySupportedRequirements(
    improvement({
      newlySupportingEvidence: [
        {
          evidenceId: "ev-1",
          evidenceType: "project",
          summary: "Built a production workflow",
          supportingRequirements: [
            {requirementId: "req-focus", originalText: "Production workflow experience"},
            {requirementId: "req-other", originalText: "Own production delivery"},
          ],
        },
        {
          evidenceId: "ev-2",
          evidenceType: "work",
          summary: "Led frontend delivery",
          supportingRequirements: [{requirementId: "req-other", originalText: "Own production delivery"}],
        },
      ],
    }),
    "req-focus",
  );

  assert.deepEqual(result, [{requirementId: "req-other", originalText: "Own production delivery"}]);
});

test("does not list evidence impact when comparison history is unverifiable", () => {
  assert.deepEqual(
    listNewlySupportedRequirements(
      improvement({
        comparable: false,
        newlySupportingEvidence: [{
          evidenceId: "ev-1",
          evidenceType: "project",
          summary: "Built a production workflow",
          supportingRequirements: [{requirementId: "req-other", originalText: "Own production delivery"}],
        }],
      }),
    ),
    [],
  );
});

test("does not diagnose incomparable history as a failure reason", () => {
  assert.equal(
    diagnoseFocusedRequirementOutcome(improvement({comparable: false}), "req-focus", true),
    "unverifiable",
  );
  assert.equal(diagnoseFocusedRequirementOutcome(null, "req-focus", true), "unverifiable");
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

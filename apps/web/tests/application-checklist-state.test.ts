import assert from "node:assert/strict";
import test from "node:test";

import {buildApplicationChecklistItems} from "../lib/application-checklist";
import {
  applicationChecklistFingerprint,
  isApplicationChecklistComplete,
  parseApplicationChecklistState,
  toggleApplicationChecklistStep,
} from "../lib/application-checklist-state";
import type {JobPreparationBundle} from "../lib/contracts";

const items = [
  {id: "highlight" as const, text: "Evidence A"},
  {id: "gap" as const, text: "Gap B"},
  {id: "interview" as const, text: "Requirement C"},
];

test("application checklist preserves only valid completion state for the current facts", () => {
  const fingerprint = applicationChecklistFingerprint(items);
  const state = parseApplicationChecklistState(JSON.stringify({
    fingerprint,
    completed: ["highlight", "highlight", "invalid", "gap"],
  }), fingerprint);

  assert.deepEqual(state.completed, ["highlight", "gap"]);
});

test("application checklist resets completion when preparation facts change", () => {
  const oldFingerprint = applicationChecklistFingerprint(items);
  const newFingerprint = applicationChecklistFingerprint([
    ...items.slice(0, 2),
    {id: "interview" as const, text: "Changed requirement"},
  ]);

  const state = parseApplicationChecklistState(JSON.stringify({
    fingerprint: oldFingerprint,
    completed: ["highlight", "gap", "interview"],
  }), newFingerprint);

  assert.deepEqual(state, {fingerprint: newFingerprint, completed: []});
});

test("application checklist completion requires all current-fingerprint steps", () => {
  const fingerprint = applicationChecklistFingerprint(items);
  const completeRaw = JSON.stringify({fingerprint, completed: ["highlight", "gap", "interview"]});
  const staleRaw = JSON.stringify({fingerprint: "stale", completed: ["highlight", "gap", "interview"]});

  assert.equal(isApplicationChecklistComplete(completeRaw, items), true);
  assert.equal(isApplicationChecklistComplete(staleRaw, items), false);
  assert.equal(isApplicationChecklistComplete(null, items), false);
  assert.equal(isApplicationChecklistComplete(completeRaw, []), false);
});

test("application checklist toggles user progress without changing its fact fingerprint", () => {
  const fingerprint = applicationChecklistFingerprint(items);
  const first = toggleApplicationChecklistStep({fingerprint, completed: []}, "highlight");
  const second = toggleApplicationChecklistStep(first, "highlight");

  assert.deepEqual(first, {fingerprint, completed: ["highlight"]});
  assert.deepEqual(second, {fingerprint, completed: []});
});

test("application checklist items are derived deterministically from the current preparation facts", () => {
  const preparation = {
    jobId: "job-1",
    factsUsable: true,
    profileId: "profile-1",
    profileVersion: 2,
    extractionId: "extract-1",
    resumeDelta: {
      highlights: [{requirementId: "r1", capability: "React", profileSkillIds: ["s1"], evidenceIds: ["e1"]}],
      evidenceGaps: [{requirementId: "r2", capability: "Trading", status: "unevidenced", profileSkillIds: ["s2"]}],
    },
    experiencePriority: {items: []},
    storyFacts: {items: []},
    interviewFacts: {items: [{
      requirementId: "r3",
      requirementType: "experience",
      requirementText: "Explain a production incident",
      importance: "must_have",
      normalizedCapability: null,
      preparationPriority: "high",
      evidenceStatus: "supported",
      profileSkillIds: [],
      evidenceIds: [],
      evidenceSummaries: [],
    }]},
    studyChecklist: {items: []},
    blockers: [],
    dbWrites: 0,
    providerCalls: 0,
    traceRunsCreated: 0,
  } satisfies JobPreparationBundle;

  const checklist = buildApplicationChecklistItems(preparation);

  assert.deepEqual(checklist.map((item) => item.id), ["highlight", "gap", "interview"]);
  assert.match(checklist[0].text, /React.*e1/);
  assert.match(checklist[1].text, /Trading.*缺少已确认 Evidence/);
  assert.match(checklist[2].text, /Explain a production incident.*high/);
});

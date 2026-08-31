import assert from "node:assert/strict";
import test from "node:test";

import {
  applicationChecklistFingerprint,
  parseApplicationChecklistState,
  toggleApplicationChecklistStep,
} from "../lib/application-checklist-state";

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

test("application checklist toggles user progress without changing its fact fingerprint", () => {
  const fingerprint = applicationChecklistFingerprint(items);
  const first = toggleApplicationChecklistStep({fingerprint, completed: []}, "highlight");
  const second = toggleApplicationChecklistStep(first, "highlight");

  assert.deepEqual(first, {fingerprint, completed: ["highlight"]});
  assert.deepEqual(second, {fingerprint, completed: []});
});

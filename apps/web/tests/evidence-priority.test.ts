import assert from "node:assert/strict";
import test from "node:test";

import type {MatchBlockerPriorityAction, UserFeedbackRecord} from "../lib/contracts";
import {consideredAffectedJobCount, selectEvidenceFocusJobId, selectNextEvidencePriority} from "../lib/evidence-priority";

function action(
  id: string,
  affectedJobCount: number,
  missingRequirementCount: number,
  affectedJobIds: string[],
): MatchBlockerPriorityAction {
  return {
    requirementType: "skill",
    normalizedCapability: id,
    affectedJobCount,
    missingRequirementCount,
    affectedJobIds,
    requirementIds: [`req-${id}`],
    examples: [`example-${id}`],
  };
}

function feedback(jobId: string, decision: UserFeedbackRecord["decision"]): UserFeedbackRecord {
  return {
    feedbackId: `feedback-${jobId}`,
    matchReportId: `report-${jobId}`,
    jobId,
    decision,
    reasons: [],
    note: null,
    createdAt: "2026-08-29T00:00:00Z",
  };
}

test("feedback only breaks exact blocker-priority ties", () => {
  const strongerFacts = action("python", 3, 4, ["job-a", "job-b", "job-c"]);
  const userFavorite = action("agent", 2, 9, ["job-favorite", "job-other"]);
  const feedbackByJobId = new Map([
    ["job-favorite", feedback("job-favorite", "interested")],
  ]);

  assert.equal(
    selectNextEvidencePriority([strongerFacts, userFavorite], feedbackByJobId, null),
    strongerFacts,
  );
});

test("interested and maybe jobs break an exact tie without changing the original fallback order", () => {
  const first = action("python", 2, 3, ["job-a", "job-b"]);
  const preferred = action("agent", 2, 3, ["job-c", "job-d"]);
  const feedbackByJobId = new Map([
    ["job-c", feedback("job-c", "interested")],
    ["job-d", feedback("job-d", "maybe")],
  ]);

  assert.equal(
    selectNextEvidencePriority([first, preferred], feedbackByJobId, null),
    preferred,
  );
  assert.equal(
    selectNextEvidencePriority([first, preferred], new Map(), null),
    first,
  );
});

test("focus job prefers the user's strongest explicit interest within the selected blocker", () => {
  const selected = action("agent", 3, 4, ["job-a", "job-b", "job-c"]);
  const feedbackByJobId = new Map([
    ["job-a", feedback("job-a", "maybe")],
    ["job-c", feedback("job-c", "interested")],
  ]);

  assert.equal(selectEvidenceFocusJobId(selected, feedbackByJobId), "job-c");
  assert.equal(selectEvidenceFocusJobId(selected, new Map()), "job-a");
});

test("explicitly rejected jobs no longer dominate the next evidence action", () => {
  const rejectedHeavy = action("python", 4, 6, ["job-a", "job-b", "job-c", "job-d"]);
  const activeTargets = action("agent", 2, 3, ["job-e", "job-f"]);
  const feedbackByJobId = new Map([
    ["job-a", feedback("job-a", "rejected")],
    ["job-b", feedback("job-b", "rejected")],
    ["job-c", feedback("job-c", "rejected")],
    ["job-e", feedback("job-e", "interested")],
  ]);

  assert.equal(consideredAffectedJobCount(rejectedHeavy, feedbackByJobId), 1);
  assert.equal(consideredAffectedJobCount(activeTargets, feedbackByJobId), 2);
  assert.equal(
    selectNextEvidencePriority([rejectedHeavy, activeTargets], feedbackByJobId, null),
    activeTargets,
  );
});

test("focus job skips rejected jobs when the blocker also affects a still-considered job", () => {
  const selected = action("agent", 2, 3, ["job-rejected", "job-open"]);
  const feedbackByJobId = new Map([
    ["job-rejected", feedback("job-rejected", "rejected")],
  ]);

  assert.equal(selectEvidenceFocusJobId(selected, feedbackByJobId), "job-open");
});

test("all-rejected actions produce no new evidence task", () => {
  const selected = action("python", 2, 3, ["job-a", "job-b"]);
  const feedbackByJobId = new Map([
    ["job-a", feedback("job-a", "rejected")],
    ["job-b", feedback("job-b", "rejected")],
  ]);

  assert.equal(selectNextEvidencePriority([selected], feedbackByJobId, null), null);
});

test("resolved requirement is excluded before feedback tie-breaking", () => {
  const resolved = action("python", 2, 3, ["job-a", "job-b"]);
  const next = action("agent", 2, 3, ["job-c", "job-d"]);
  const feedbackByJobId = new Map([
    ["job-a", feedback("job-a", "interested")],
  ]);

  assert.equal(
    selectNextEvidencePriority([resolved, next], feedbackByJobId, "req-python"),
    next,
  );
});

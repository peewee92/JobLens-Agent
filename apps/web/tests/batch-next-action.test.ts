import assert from "node:assert/strict";
import test from "node:test";

import {selectBatchNextAction} from "../lib/batch-next-action";

const base = {
  pendingFeedbackJobIds: [] as string[],
  matchReadyJobIds: [] as string[],
  requirementBlockedJobIds: [] as string[],
  evidenceAvailable: false,
  evidenceImpactCount: 0,
  maybeJobIds: [] as string[],
  unverifiableCount: 0,
};

test("batch next action keeps the main-loop priority stable", () => {
  assert.deepEqual(selectBatchNextAction({
    pendingFeedbackJobIds: ["feedback-job"],
    matchReadyJobIds: ["match-job"],
    requirementBlockedJobIds: ["requirement-job"],
    evidenceAvailable: true,
    evidenceImpactCount: 2,
    maybeJobIds: ["maybe-job"],
    unverifiableCount: 1,
  }), {kind: "feedback", jobId: "feedback-job"});

  assert.deepEqual(selectBatchNextAction({
    ...base,
    matchReadyJobIds: ["match-a", "match-b"],
    requirementBlockedJobIds: ["requirement-job"],
    evidenceAvailable: true,
    maybeJobIds: ["maybe-job"],
  }), {kind: "match", count: 2});

  assert.deepEqual(selectBatchNextAction({
    ...base,
    requirementBlockedJobIds: ["requirement-a", "requirement-b"],
    evidenceAvailable: true,
    maybeJobIds: ["maybe-job"],
  }), {kind: "requirement", jobId: "requirement-a", count: 2});

  assert.deepEqual(selectBatchNextAction({
    ...base,
    evidenceAvailable: true,
    evidenceImpactCount: 3,
    maybeJobIds: ["maybe-job"],
  }), {kind: "evidence", impactCount: 3});

  assert.deepEqual(selectBatchNextAction({...base, maybeJobIds: ["maybe-a", "maybe-b"]}), {
    kind: "maybe",
    jobId: "maybe-a",
    count: 2,
  });

  assert.deepEqual(selectBatchNextAction({...base, unverifiableCount: 2}), {kind: "unverifiable", count: 2});
  assert.deepEqual(selectBatchNextAction(base), {kind: "next-batch"});
});

import assert from "node:assert/strict";
import test from "node:test";
import {readEvalReviewReceipt} from "../lib/eval-review-receipt";

const saved = {
  id: "review_1", evalRunId: "run_1", decision: "rejected",
  reviewer: "合成审核员", notes: "合成的审核说明，用于确认显示回执。", reviewedAt: "2026-11-19T04:00:00Z",
};

test("an authoritative review receipt can replace the form without reloading the page", () => {
  assert.deepEqual(readEvalReviewReceipt(saved, "run_1", "rejected"), saved);
});

test("another run, another decision or an incomplete receipt does not count as saved", () => {
  assert.equal(readEvalReviewReceipt(saved, "run_2", "rejected"), null);
  assert.equal(readEvalReviewReceipt(saved, "run_1", "accepted"), null);
  assert.equal(readEvalReviewReceipt({id: "review_1", evalRunId: "run_1", decision: "rejected"}, "run_1", "rejected"), null);
});

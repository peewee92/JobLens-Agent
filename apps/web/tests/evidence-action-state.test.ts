import assert from "node:assert/strict";
import test from "node:test";

import {
  EVIDENCE_ACTION_MAX_AGE_MS,
  evidenceActionStageLabel,
  parseEvidenceActionSnapshot,
} from "../lib/evidence-action-state";

const now = 1_900_000_000_000;

test("parses a bounded recoverable evidence action snapshot", () => {
  const parsed = parseEvidenceActionSnapshot(JSON.stringify({
    requirementId: " req-1 ",
    jobId: "job-1",
    capability: "Python",
    requirementText: "需要 Python 项目经验",
    stage: "pending",
    updatedAt: now - 1_000,
  }), now);

  assert.deepEqual(parsed, {
    requirementId: "req-1",
    jobId: "job-1",
    capability: "Python",
    requirementText: "需要 Python 项目经验",
    stage: "pending",
    updatedAt: now - 1_000,
  });
});

test("drops stale or malformed evidence action snapshots", () => {
  assert.equal(parseEvidenceActionSnapshot("not-json", now), null);
  assert.equal(parseEvidenceActionSnapshot(JSON.stringify({
    requirementId: "req-1",
    stage: "pending",
    updatedAt: now - EVIDENCE_ACTION_MAX_AGE_MS - 1,
  }), now), null);
  assert.equal(parseEvidenceActionSnapshot(JSON.stringify({
    requirementId: "req-1",
    stage: "invented",
    updatedAt: now,
  }), now), null);
});

test("keeps the three user-facing action stages explicit", () => {
  assert.equal(evidenceActionStageLabel("pending"), "待核实");
  assert.equal(evidenceActionStageLabel("evidence_saved"), "已核实，等待可比较的 Re-match");
  assert.equal(evidenceActionStageLabel("rematch_verified"), "Re-match 已验证");
});

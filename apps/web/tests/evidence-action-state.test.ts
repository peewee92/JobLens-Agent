import assert from "node:assert/strict";
import test from "node:test";

import {
  EVIDENCE_ACTION_MAX_AGE_MS,
  evidenceActionStageLabel,
  parseEvidenceActionSnapshot,
  parseEvidenceActionState,
  transitionEvidenceActionState,
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

test("migrates the previous single-snapshot browser state without losing the active action", () => {
  const legacy = JSON.stringify({
    requirementId: "req-legacy",
    jobId: "job-legacy",
    capability: "React",
    requirementText: "需要 React 项目经验",
    stage: "pending",
    updatedAt: now,
  });
  const state = parseEvidenceActionState(legacy, now);

  assert.equal(state?.current?.requirementId, "req-legacy");
  assert.deepEqual(state?.recentCompleted, []);
});

test("moves a verified action into bounded completed history when a successor takes over", () => {
  const current = parseEvidenceActionSnapshot(JSON.stringify({
    requirementId: "req-1",
    jobId: "job-1",
    capability: "Python",
    requirementText: "需要 Python 项目经验",
    stage: "rematch_verified",
    updatedAt: now - 1_000,
  }), now)!;
  const successor = {...current, requirementId: "req-2", capability: "FastAPI", stage: "pending" as const, updatedAt: now};
  const state = transitionEvidenceActionState({current, recentCompleted: []}, successor, true);

  assert.equal(state.current?.requirementId, "req-2");
  assert.equal(state.recentCompleted[0]?.requirementId, "req-1");
  assert.equal(state.recentCompleted[0]?.stage, "completed");
  assert.deepEqual(parseEvidenceActionState(JSON.stringify(state), now), state);
});

test("keeps the four user-facing action stages explicit", () => {
  assert.equal(evidenceActionStageLabel("pending"), "待核实");
  assert.equal(evidenceActionStageLabel("evidence_saved"), "已核实，等待可比较的 Re-match");
  assert.equal(evidenceActionStageLabel("rematch_verified"), "Re-match 已验证");
  assert.equal(evidenceActionStageLabel("completed"), "已完成");
});

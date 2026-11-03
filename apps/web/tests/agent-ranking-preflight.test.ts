import assert from "node:assert/strict";
import test from "node:test";
import {rankingPreflight, rankingScope} from "../lib/agent-ranking-preflight";

test("partial and empty rankings keep the requested scope visible", () => {
  const missing = {jobId: "a", reason: "report_missing", staleReasons: []};
  assert.deepEqual(rankingPreflight(["a", "b"], {items: [{jobId: "b", targetCandidate: true}], omissions: [missing]}), {scope: rankingScope(["a", "b"]), ranked: ["b"], candidates: ["b"], insufficient: [], omissions: [missing]});
  assert.deepEqual(rankingPreflight(["a"], {items: [], omissions: [missing]}).omissions, [missing]);
});
test("a readable report without a supported target is not a proposal", () => {
  const result = rankingPreflight(["a", "b"], {items: [{jobId: "a", targetCandidate: false}, {jobId: "b", targetCandidate: true}], omissions: []});
  assert.deepEqual(result.ranked, ["a", "b"]);
  assert.deepEqual(result.candidates, ["b"]);
  assert.deepEqual(result.insufficient, ["a"]);
  assert.deepEqual(rankingPreflight(["a"], {items: [{jobId: "a", targetCandidate: false}], omissions: []}).candidates, []);
});
test("selection order is irrelevant but scope changes invalidate the check", () => {
  assert.equal(rankingScope(["a", "b"]), rankingScope(["b", "a"]));
  assert.notEqual(rankingScope(["a", "b"]), rankingScope(["a"]));
});
test("malformed or unexpected ranking results do not enable a run", () => {
  for (const response of [null, {}, {items: [null], omissions: []}, {items: [{jobId: "a"}], omissions: []}, {items: [{jobId: "other", targetCandidate: true}], omissions: []}, {items: [{jobId: "a", targetCandidate: true}, {jobId: "a", targetCandidate: false}], omissions: []}, {items: [], omissions: []}, {items: [], omissions: [{jobId: "a", reason: "report_stale", staleReasons: []}]}]) {
    assert.throws(() => rankingPreflight(["a"], response));
  }
  assert.throws(() => rankingPreflight([], {items: []}));
  assert.throws(() => rankingPreflight(["a", "a"], {items: []}));
});

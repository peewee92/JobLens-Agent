import test from "node:test";
import assert from "node:assert/strict";
import {mergeImportMatchRemainder, splitAnalysisScopes, splitImportMatchBatch} from "../lib/import-match-batching";

test("requests at most 50 and retains deferred and untouched jobs in order", () => {
  const all = Array.from({length: 75}, (_, i) => `job_${i}`);
  const first = splitImportMatchBatch(all);
  assert.equal(first.requestJobIds.length, 50);
  assert.deepEqual(first.untouchedJobIds, all.slice(50));
  const pending = mergeImportMatchRemainder(first.requestJobIds.slice(5), first.untouchedJobIds);
  assert.deepEqual(pending, all.slice(5));
  assert.equal(splitImportMatchBatch(pending).requestJobIds.length, 50);
  assert.deepEqual(mergeImportMatchRemainder(["b"], ["b", "c"]), ["b", "c"]);
});

test("successful results are split into valid scopes without truncation", () => {
  const all = Array.from({length: 101}, (_, i) => `job_${i}`);
  const scopes = splitAnalysisScopes(all);
  assert.deepEqual(scopes.map(x => x.length), [50, 50, 1]);
  assert.deepEqual(scopes.flat(), all);
  assert.deepEqual(splitAnalysisScopes([]), []);
});

test("continue label does not reset when server refresh changes the input prop", async () => {
  const {importMatchButtonLabel} = await import("../lib/import-match-batching");
  assert.equal(importMatchButtonLabel(51, false, false), "匹配这批已准备岗位（5 个）");
  assert.equal(importMatchButtonLabel(46, true, false), "继续匹配剩余 46 个");
  assert.equal(importMatchButtonLabel(46, true, true), "正在匹配…");
});

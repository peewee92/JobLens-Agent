import test from "node:test";
import assert from "node:assert/strict";
import {fetchImportFeedbackBatches} from "../lib/import-feedback-batches";
import type {UserFeedbackHistory} from "../lib/contracts";

const empty = (): UserFeedbackHistory => ({feedback: [], dbWrites: 0, providerCalls: 0, traceRunsCreated: 0});
test("51 reports are read in bounded batches without losing or repeating ids", async () => {
  const ids = Array.from({length: 51}, (_, i) => `report-${i}`);
  const calls: string[][] = [];
  const result = await fetchImportFeedbackBatches([...ids, ids[0]], async batch => {calls.push(batch); return empty();});
  assert.deepEqual(calls.map(batch => batch.length), [50, 1]);
  assert.deepEqual(calls.flat(), ids);
  assert.deepEqual(result, empty());
});
test("a failed batch rejects rather than treating missing feedback as absent", async () => {
  const ids = Array.from({length: 51}, (_, i) => `report-${i}`);
  await assert.rejects(fetchImportFeedbackBatches(ids, async batch => {
    if (batch.length === 1) throw new Error("unavailable");
    return empty();
  }), /unavailable/);
});

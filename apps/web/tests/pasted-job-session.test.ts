import {strict as assert} from "node:assert";
import test from "node:test";
import {lastPastedJobScope, savePastedJobScope} from "../lib/pasted-job-session";

test("recovers only the last confirmed IDs and ignores empty saves", () => {
  let value: string | null = null;
  const storage = {getItem: () => value, setItem: (_: string, v: string) => { value = v; }};
  assert.deepEqual(lastPastedJobScope(storage), []);
  savePastedJobScope(storage, ["job_1", "job_2"]);
  savePastedJobScope(storage, []);
  assert.equal(value, '["job_1","job_2"]');
  assert.deepEqual(lastPastedJobScope(storage), ["job_1", "job_2"]);
  value = '["job_1",42]';
  assert.deepEqual(lastPastedJobScope(storage), []);
  value = '["job_1","job_1"]';
  assert.deepEqual(lastPastedJobScope(storage), []);
});

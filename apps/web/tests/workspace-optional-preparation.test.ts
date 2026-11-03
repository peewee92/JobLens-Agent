import assert from "node:assert/strict";
import test from "node:test";
import {readOptionalPreparation} from "../lib/workspace-optional-preparation";
function apiError(status: number, code: string) {
  return Object.assign(new Error(code), {status, code});
}
test("stale preparation does not hide historical workspace", async () => {
  assert.equal(await readOptionalPreparation(async () => { throw apiError(409, "application_workspace_facts_stale"); }), null);
  assert.deepEqual(await readOptionalPreparation(async () => ({value: 1})), {value: 1});
});
test("unrelated failures are not hidden as stale preparation", async () => {
  await assert.rejects(readOptionalPreparation(async () => { throw apiError(503, "database_error"); }), /database_error/);
  await assert.rejects(readOptionalPreparation(async () => { throw apiError(500, "application_workspace_facts_stale"); }), /facts_stale/);
});

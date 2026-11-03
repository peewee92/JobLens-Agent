import assert from "node:assert/strict";
import test from "node:test";
import {readFile} from "node:fs/promises";

import {isSystemReadiness, readinessMessage, type SystemReadiness} from "@/lib/system-readiness";

const ready: SystemReadiness = {
  ready: true, code: "ready", checks: {database: "passed", migrations: "passed", tables: "passed"},
  currentRevisions: ["head"], requiredRevisions: ["head"], missingTables: [],
};

test("readiness decoder accepts ready and actionable 503 payloads", () => {
  assert.equal(isSystemReadiness(ready), true);
  assert.equal(isSystemReadiness({...ready, ready: false, code: "migration_required", checks: {...ready.checks, migrations: "failed"}}), true);
});

test("readiness decoder fails closed on contradictory or unknown payloads", () => {
  for (const invalid of [null, {}, {error: {message: "private SQL error"}}, {...ready, code: "unexpected"}, {...ready, ready: false}, {...ready, checks: {...ready.checks, tables: "failed"}}, {...ready, missingTables: ["jobs"]}, {...ready, currentRevisions: "head"}, {...ready, currentRevisions: ["old"]}, {...ready, extra: "unexpected"}]) {
    assert.equal(isSystemReadiness(invalid), false);
  }
});

test("readiness failures explain repair without encouraging data deletion", () => {
  assert.match(readinessMessage("migration_required"), /备份.*副本.*不会自动修改/);
  assert.match(readinessMessage("schema_incomplete"), /不要直接重建或清空/);
  assert.match(readinessMessage("database_unavailable"), /连接配置和访问权限/);
});

test("readiness vocabulary matches the shared contract", async () => {
  const contract = JSON.parse(await readFile(new URL("../../../packages/contracts/schemas/system-readiness.schema.json", import.meta.url), "utf8"));
  assert.deepEqual(Object.keys(ready).sort(), contract.required.sort());
  for (const code of contract.properties.code.enum) assert.equal(typeof readinessMessage(code), "string");
});

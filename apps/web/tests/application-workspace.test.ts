import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import assert from "node:assert/strict";

const root = process.cwd();

function source(relative: string) {
  return fs.readFileSync(path.join(root, relative), "utf8");
}

test("job preparation exposes the application workspace entry", () => {
  const page = source("app/jobs/[id]/prepare/page.tsx");
  assert.match(page, /ApplicationWorkspaceEntry/);
  assert.match(page, /统一查看岗位简历、面试、行动、Evidence 回流、投递状态与下一建议动作/);
});

test("application workspace renders deterministic next action and execution facts", () => {
  const page = source("app/applications/[id]/page.tsx");
  assert.match(page, /nextBestAction\.label/);
  assert.match(page, /actionOpen/);
  assert.match(page, /evidencePendingConfirmation/);
  assert.match(page, /系统不会自动投递或替你确认职业事实/);
});

test("workspace creation uses a stable per-job idempotency key", () => {
  const component = source("components/application-workspace-entry.tsx");
  assert.match(component, /web-application-workspace:\$\{jobId\}/);
  assert.match(component, /actorId: "local-user"/);
});

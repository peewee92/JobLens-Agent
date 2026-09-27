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

test("application workspace can create and advance real execution actions", () => {
  const page = source("app/applications/[id]/page.tsx");
  const controls = source("components/application-action-controls.tsx");
  const createProxy = source("app/api/application-workspaces/[id]/actions/route.ts");
  const statusProxy = source("app/api/application-workspaces/[id]/actions/[actionId]/status/route.ts");

  assert.match(page, /ApplicationActionControls/);
  assert.match(controls, /把学习清单建立为行动/);
  assert.match(controls, /expectedStatus: action\.status/);
  assert.match(controls, /newStatus: transition\.status/);
  assert.match(controls, /web-study-actions-\$\{workspaceId\}/);
  assert.match(createProxy, /application-workspaces\/\$\{encodeURIComponent\(id\)\}\/actions/);
  assert.match(statusProxy, /actions\/\$\{encodeURIComponent\(actionId\)\}\/status/);
});

test("workspace creation uses a stable per-job idempotency key", () => {
  const component = source("components/application-workspace-entry.tsx");
  assert.match(component, /web-application-workspace:\$\{jobId\}/);
  assert.match(component, /actorId: "local-user"/);
});

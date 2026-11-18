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
  assert.match(page, /统一查看岗位简历、面试、行动、经历补充与投递状态/);
});

test("application workspace renders deterministic next action and execution facts", () => {
  const page = source("app/applications/[id]/page.tsx");
  assert.match(page, /nextBestAction\.label/);
  assert.match(page, /actionOpen/);
  assert.match(page, /evidencePendingConfirmation/);
  assert.match(page, /系统不会替你投递或确认经历/);
});

test("application workspace lets the user save and explicitly review a grounded resume variant", () => {
  const page = source("app/applications/[id]/page.tsx");
  const controls = source("components/application-resume-controls.tsx");
  const saveProxy = source("app/api/application-workspaces/[id]/resume-variants/route.ts");
  const reviewProxy = source("app/api/application-workspaces/[id]/resume-variants/[variantId]/review/route.ts");

  assert.match(page, /ApplicationResumeControls/);
  assert.match(controls, /仍有 .* 项岗位要求还缺可引用的真实经历/);
  assert.match(controls, /保存岗位简历草稿/);
  assert.match(controls, /确认已人工审核/);
  assert.match(controls, /expectedStatus: "draft"/);
  assert.match(controls, /web-resume-variant-\$\{workspaceId\}/);
  assert.match(saveProxy, /application-workspaces\/\$\{encodeURIComponent\(id\)\}\/resume-variants/);
  assert.match(reviewProxy, /resume-variants\/\$\{encodeURIComponent\(variantId\)\}\/review/);
});

test("application workspace lets the user explicitly update application status", () => {
  const page = source("app/applications/[id]/page.tsx");
  const controls = source("components/application-status-controls.tsx");
  const proxy = source("app/api/application-workspaces/[id]/status/route.ts");

  assert.match(page, /ApplicationStatusControls/);
  assert.match(controls, /投递状态只由你显式更新/);
  assert.match(controls, /expectedStatus: currentStatus/);
  assert.match(controls, /newStatus: selectedStatus/);
  assert.match(controls, /useProgressRequest/);
  assert.doesNotMatch(controls, /Date.now/);
  assert.match(proxy, /application-workspaces\/\$\{encodeURIComponent\(id\)\}\/status/);
});

test("application workspace can create and advance real execution actions", () => {
  const page = source("app/applications/[id]/page.tsx");
  const controls = source("components/application-action-controls.tsx");
  const createProxy = source("app/api/application-workspaces/[id]/actions/route.ts");
  const statusProxy = source("app/api/application-workspaces/[id]/actions/[actionId]/status/route.ts");

  assert.match(page, /ApplicationActionControls/);
  assert.match(controls, /把学习清单建立为行动/);
  assert.match(controls, /expectedStatus:\s*action\.status/);
  assert.match(controls, /newStatus:\s*transition\.status/);
  assert.match(controls, /web-study-actions-\$\{workspaceId\}/);
  assert.match(createProxy, /application-workspaces\/\$\{encodeURIComponent\(id\)\}\/actions/);
  assert.match(statusProxy, /actions\/\$\{encodeURIComponent\(actionId\)\}\/status/);
});

test("application workspace confirms facts and routes legacy workspaces to a new analysis", () => {
  const page = source("app/applications/[id]/page.tsx");
  const controls = source("components/application-evidence-controls.tsx");
  const createProxy = source("app/api/application-workspaces/[id]/actions/[actionId]/evidence-proposals/route.ts");
  const confirmProxy = source("app/api/application-workspaces/[id]/evidence-proposals/[proposalId]/confirm/route.ts");
  const rematchProxy = source("app/api/application-workspaces/[id]/evidence-proposals/[proposalId]/rematch/route.ts");

  assert.match(page, /ApplicationEvidenceControls/);
  assert.match(controls, /完成准备行动不会自动升级能力/);
  assert.match(controls, /确认这是真实职业事实/);
  assert.match(controls, /核对该岗位并准备新分析/);
  assert.doesNotMatch(controls, /web-rematch-\$\{proposal\.proposalId\}/);
  assert.match(createProxy, /evidence-proposals/);
  assert.match(confirmProxy, /\/confirm/);
  assert.match(rematchProxy, /\/rematch/);
});

test("application workspace runs grounded interview practice without provider scoring", () => {
  const page = source("app/applications/[id]/page.tsx");
  const controls = source("components/application-interview-controls.tsx");
  const reviewProxy = source("app/api/application-workspaces/[id]/interview/questions/[questionId]/review/route.ts");

  assert.match(page, /ApplicationInterviewControls/);
  assert.match(page, /回答只核对已确认的经历是否可引用/);
  assert.match(controls, /你的真实回答/);
  assert.match(controls, /allowedEvidenceIds/);
  assert.match(controls, /按真实经历核对回答/);
  assert.match(controls, /修改后重新审核/);
  assert.doesNotMatch(controls, /Provider calls:/);
  assert.match(controls, /evidenceSummaries.get/);
  assert.match(reviewProxy, /interview\/questions\/\$\{encodeURIComponent\(questionId\)\}\/review/);
});

test("workspace creation uses a stable per-job idempotency key", () => {
  const component = source("components/application-workspace-entry.tsx");
  assert.match(component, /web-application-workspace:\$\{jobId\}/);
  assert.match(component, /actorId: "local-user"/);
});

import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";

const source = (relative: string) => fs.readFileSync(path.join(process.cwd(), relative), "utf8");

test("production navigation stays on product routes, not review surfaces", () => {
  const routes = fs.readdirSync(path.join(process.cwd(), "app"), {recursive: true}).map(String);
  assert.ok(!routes.some(name => /(?:^|\/)(states|design)(?:\/|$)|prototype/.test(name)));
  assert.doesNotMatch(source("app/layout.tsx"), /状态地图|组件样例|页面地图|审稿选项|prepare-v3\.html/);
});

test("original preview displays only the existing read-only description", () => {
  const adapter = source("app/api/jobs/[id]/original/route.ts");
  assert.match(adapter, /export async function GET/);
  assert.doesNotMatch(adapter, /export async function (POST|PUT|PATCH|DELETE)/);
  assert.match(adapter, /Response\.json\(\{description: job\.description\}/);
});

test("paid test and resume recovery query their saved receipt instead of resending", () => {
  assert.match(source("components/model-connection.tsx"), /fetch\(`\/api\/byok\/profile-calls\/\$\{encodeURIComponent\(action\)\}`/);
  assert.match(source("components/resume-proposal-panel.tsx"), /workspaceFetch\(`\/api\/byok\/profile-calls\/\$\{encodeURIComponent\(pendingAction\)\}`/);
  assert.match(source("components/resume-proposal-panel.tsx"), /acknowledgedPriorRequestId/);
  assert.match(source("lib/backend.ts"), /reading && !init\?\.signal \? AbortSignal\.timeout/);
});

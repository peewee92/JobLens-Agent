import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import test from "node:test";

const root = new URL("../", import.meta.url);

function read(path: string): string {
  return readFileSync(new URL(path, root), "utf8");
}

test("career agent page exposes the minimal durable HITL flow", () => {
  const page = read("app/agent/page.tsx");
  const panel = read("components/career-agent-hitl-panel.tsx");

  assert.match(page, /CareerAgentHitlPanel/);
  assert.match(panel, /localStorage/);
  assert.match(panel, /\/api\/career-agent\/runs/);
  assert.match(panel, /approve/);
  assert.match(panel, /edit/);
  assert.match(panel, /reject/);
  assert.match(panel, /pendingApproval/);
  assert.match(panel, /gapResultFingerprint/);
  assert.match(panel, /Career Agent Chat/);
  assert.match(panel, /你的请求/);
  assert.match(panel, /当前计划/);
  assert.match(panel, /执行状态/);
  assert.match(panel, /查看依据/);
});

test("web proxy keeps durable run start, load and resume behind same-origin routes", () => {
  const collectionRoute = read("app/api/career-agent/runs/route.ts");
  const threadRoute = read("app/api/career-agent/runs/[threadId]/route.ts");
  const resumeRoute = read("app/api/career-agent/runs/[threadId]/resume/route.ts");

  assert.match(collectionRoute, /\/api\/v1\/career-agent\/runs/);
  assert.match(threadRoute, /career-agent\/runs\/\$\{encodeURIComponent\(threadId\)\}/);
  assert.match(resumeRoute, /career-agent\/runs\/\$\{encodeURIComponent\(threadId\)\}\/resume/);
});

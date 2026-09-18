import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import test from "node:test";

import {
  CareerAgentRunHttpError,
  buildGapHandoffHref,
  shouldForgetPendingThread,
} from "../lib/career-agent-run";

const root = new URL("../", import.meta.url);

function read(path: string): string {
  return readFileSync(new URL(path, root), "utf8");
}

test("pending durable run is forgotten only when the backend says it no longer exists", () => {
  assert.equal(shouldForgetPendingThread(new CareerAgentRunHttpError(404, "missing")), true);
  assert.equal(shouldForgetPendingThread(new CareerAgentRunHttpError(503, "temporary outage")), false);
  assert.equal(shouldForgetPendingThread(new TypeError("network unavailable")), false);
});

test("completed agent run hands the confirmed cohort to the existing readable gap workspace", () => {
  assert.equal(
    buildGapHandoffHref(["job_2", "job_1", "job_2", "../unsafe"]),
    "/gaps?jobId=job_2&jobId=job_1&from=agent",
  );

  const agentPanel = read("components/career-agent-hitl-panel.tsx");
  const gapPage = read("app/gaps/page.tsx");
  const gapPanel = read("components/target-cohort-gap-panel.tsx");

  assert.match(agentPanel, /重试恢复/);
  assert.match(agentPanel, /查看能力差距结果/);
  assert.match(gapPage, /initialJobIds/);
  assert.match(gapPanel, /initialJobIds/);
  assert.match(gapPanel, /已带入 Agent 确认的/);
});

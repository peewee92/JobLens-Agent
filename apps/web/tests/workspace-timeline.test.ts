import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import {renderToStaticMarkup} from "react-dom/server";
import {WorkspaceTimeline} from "../components/workspace-timeline";
import type {ApplicationTimelineEvent} from "../lib/contracts";

const event = (eventId: string, eventType: string, fromStatus: string | null = null, toStatus: string | null = null): ApplicationTimelineEvent => ({
  eventId, eventType, fromStatus, toStatus, workspaceId: "workspace", actorId: "actor", createdAt: "2026-10-27T00:00:00Z",
});
const render = (events: ApplicationTimelineEvent[]) => renderToStaticMarkup(React.createElement(WorkspaceTimeline, {events}));

test("recent changes explain actual events and show timestamps", () => {
  const html = render([event("1", "workspace_created", null, "preparing"), event("2", "action_completed"), event("3", "evidence_confirmed"), event("4", "status_changed", "preparing", "applied")]);
  assert.match(html, /求职状态已更新：准备中 → 已投递/);
  assert.match(html, /已确认一项职业事实/);
  assert.match(html, /已完成一项行动/);
  assert.match(html, /已创建求职工作区：初始状态为准备中/);
  assert.match(html, /dateTime="2026-10-27T00:00:00Z"/);
  assert.ok(html.indexOf("求职状态已更新") < html.indexOf("已完成一项行动"));
  assert.doesNotMatch(html, /action_completed|evidence_confirmed/);
});

test("only six latest entries are shown, without guessing unknown events or statuses", () => {
  const html = render([event("0", "workspace_created"), ...Array.from({length: 5}, (_, i) => event(String(i + 1), "resume_variant_saved")), event("6", "unknown_event", "untrusted", "untrusted"), event("7", "status_changed", null, "untrusted")]);
  assert.doesNotMatch(html, /已创建求职工作区|unknown_event|untrusted/);
  assert.match(html, /其他工作区记录/);
  assert.match(html, /求职状态已更新：未记录 → 未知状态/);
  assert.equal((html.match(/<li>/g) ?? []).length, 6);
  assert.match(render([]), /暂无时间线事件/);
});

import assert from "node:assert/strict";
import test from "node:test";
import {
  saveRunCommand, loadRunCommand, clearRunCommand, parseSavedRunCommand,
  sendRunCommand, commandResolution, runHref, type SavedRunCommand,
} from "../lib/career-agent-commands";
import type {CareerAgentRunState} from "../lib/contracts";

function storage() {
  const values = new Map<string, string>();
  return {getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => {values.set(key, value);},
    removeItem: (key: string) => {values.delete(key);}};
}
const start: SavedRunCommand = {version: 1, kind: "start", threadId: "thread", body: {
  threadId: "thread", runId: "run", requestId: "request", jobIds: ["j1", "j2"], topN: 2,
}};
const decision: SavedRunCommand = {version: 1, kind: "decision", threadId: "thread", body: {
  interruptId: "interrupt", actionId: "action", decision: "approve", selectedJobIds: [],
}};

test("start is durably recorded before send and network retry keeps the exact request body", async () => {
  const saved = storage();
  const bodies: string[] = [];
  const fetcher: typeof fetch = async (input, init) => {
    assert.deepEqual(loadRunCommand(saved, "thread"), start);
    assert.equal(input, "/api/career-agent/runs");
    bodies.push(String(init?.body));
    throw new TypeError("network unavailable");
  };
  await assert.rejects(sendRunCommand(saved, start, fetcher), /network unavailable/);
  const restored = loadRunCommand(saved, "thread")!;
  await assert.rejects(sendRunCommand(saved, restored, fetcher), /network unavailable/);
  assert.equal(bodies.length, 2);
  assert.equal(bodies[0], bodies[1]);
  assert.equal(JSON.parse(bodies[0]).requestId, "request");
});

test("decision retry preserves action and cannot overwrite an unresolved command", async () => {
  const saved = storage();
  const calls: string[] = [];
  const fetcher: typeof fetch = async (input, init) => {
    assert.equal(input, "/api/career-agent/runs/thread/resume");
    calls.push(String(init?.body));
    throw new TypeError("response lost");
  };
  await assert.rejects(sendRunCommand(saved, decision, fetcher));
  await assert.rejects(sendRunCommand(saved, loadRunCommand(saved, "thread")!, fetcher));
  assert.equal(calls[0], calls[1]);
  assert.throws(() => saveRunCommand(saved, {...decision, body: {...decision.body, actionId: "other"}}), /不能覆盖/);
  assert.deepEqual(loadRunCommand(saved, "thread"), decision);
});

test("storage failure prevents transmission, malformed or unrelated local data is ignored", async () => {
  let calls = 0;
  const broken = {...storage(), setItem() {throw new Error("quota exhausted");}};
  const fetcher: typeof fetch = async () => {calls++; return new Response();};
  await assert.rejects(sendRunCommand(broken, start, fetcher), /quota exhausted/);
  assert.equal(calls, 0);
  for (const raw of ["bad json", "null", "{}", JSON.stringify({...start, version: 99}),
    JSON.stringify({...start, threadId: "other"}), JSON.stringify({...start, body: {...start.body, topN: 99}})]) {
    assert.equal(parseSavedRunCommand(raw, "thread"), null);
  }
});

test("a competing browser write cannot cause another command to be transmitted", async () => {
  const base = storage();
  let calls = 0;
  const saved = {...base, getItem(key: string) {
    const raw = base.getItem(key);
    return raw ? JSON.stringify(decision) : null;
  }};
  await assert.rejects(sendRunCommand(saved, start, async () => {calls++; return new Response();}), /尚未发送/);
  assert.equal(calls, 0);
});

test("server action identity resolves accepted and superseded decisions without guessing", () => {
  const state = {threadId: "thread", decisionActionId: null} as CareerAgentRunState;
  assert.equal(commandResolution(start, state), "accepted");
  assert.equal(commandResolution(decision, state), "pending");
  assert.equal(commandResolution(decision, {...state, decisionActionId: "action"}), "accepted");
  assert.equal(commandResolution(decision, {...state, decisionActionId: "other"}), "superseded");
  assert.equal(commandResolution(decision, {...state, threadId: "another"}), "pending");
});

test("clearing an acknowledged command does not delete a newer scoped command", () => {
  const saved = storage();
  saveRunCommand(saved, start);
  clearRunCommand(saved, start);
  saveRunCommand(saved, decision);
  clearRunCommand(saved, start);
  assert.deepEqual(loadRunCommand(saved, "thread"), decision);
  clearRunCommand(saved, decision);
  assert.equal(loadRunCommand(saved, "thread"), null);
  assert.equal(runHref("a/b?c"), "/agent?threadId=a%2Fb%3Fc");
});

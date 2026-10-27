import test from "node:test";
import assert from "node:assert/strict";
import {readWorkspaceFactCommand, sendWorkspaceFactCommand, clearWorkspaceFactCommand, type WorkspaceFactCommand} from "../lib/workspace-fact-command";

function storage() {
  const values = new Map<string, string>();
  return {getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => {values.set(key, value);}, removeItem: (key: string) => {values.delete(key);}};
}
const command: WorkspaceFactCommand = {version: 1, workspaceId: "workspace", commandId: "original", path: "/api/application-workspaces/workspace/actions/action/evidence-proposals",
  body: {actorId: "local-user", idempotencyKey: "original", evidenceSummary: "Actual user-authored outcome"}};

test("journal is saved before sending; uncertain network result survives refresh and exact replay", async () => {
  const store = storage();
  let calls = 0;
  const send = async (path: Parameters<typeof fetch>[0], options?: RequestInit) => {
    calls++;
    assert.deepEqual(readWorkspaceFactCommand(store, "workspace"), command);
    assert.equal(path, command.path);
    assert.deepEqual(JSON.parse(options!.body as string), command.body);
    if (calls === 1) throw new Error("connection lost after send");
    return new Response("{}", {status: 201});
  };
  await assert.rejects(sendWorkspaceFactCommand(store, command, send), /connection lost/);
  const restored = readWorkspaceFactCommand(store, "workspace")!;
  assert.deepEqual(restored, command);
  assert.equal(calls, 1); // Reading/rendering never sends anything.
  await sendWorkspaceFactCommand(store, restored, send);
  assert.equal(calls, 2);
  assert.equal(readWorkspaceFactCommand(store, "workspace"), null);
});

test("new input cannot replace an uncertain command; 503 remains recoverable", async () => {
  const store = storage();
  await sendWorkspaceFactCommand(store, command, async () => new Response("{}", {status: 503}));
  let calls = 0;
  await assert.rejects(sendWorkspaceFactCommand(store, {...command, commandId: "new"}, async () => {calls++; return new Response("{}");}), /不会覆盖/);
  assert.equal(calls, 0);
  assert.equal(readWorkspaceFactCommand(store, "workspace")?.rejected, undefined);
});

test("known rejection permits explicit discard but an old callback cannot clear a newer command", async () => {
  const store = storage();
  await sendWorkspaceFactCommand(store, command, async () => new Response("{}", {status: 409}));
  const rejected = readWorkspaceFactCommand(store, "workspace")!;
  assert.equal(rejected.rejected, true);
  clearWorkspaceFactCommand(store, rejected);
  assert.equal(readWorkspaceFactCommand(store, "workspace"), null);
  const next = {...command, commandId: "next"};
  store.setItem("joblens.workspaceFactCommand.workspace", JSON.stringify(next));
  clearWorkspaceFactCommand(store, command);
  assert.deepEqual(readWorkspaceFactCommand(store, "workspace"), next);
});

test("journal never sends external, cross-workspace or model commands", async () => {
  for (const path of ["https://example.com/facts", "/api/application-workspaces/other/actions/action/evidence-proposals",
    "/api/application-workspaces/workspace/evidence-proposals/id/rematch", "/api/application-workspaces/workspace/../../other"]) {
    const store = storage(); let calls = 0;
    await assert.rejects(sendWorkspaceFactCommand(store, {...command, path}, async () => {calls++; return new Response("{}");}), /不属于/);
    assert.equal(calls, 0);
  }
});

test("unavailable storage, corrupted record and disappearing cross-tab record never start a request", async () => {
  let calls = 0;
  const send = async () => {calls++; return new Response("{}");};
  const unavailable = {...storage(), setItem() {throw new Error("storage denied");}};
  await assert.rejects(sendWorkspaceFactCommand(unavailable, command, send), /storage denied/);
  const disappearing = {...storage(), setItem() { /* tab removed record */ }};
  await assert.rejects(sendWorkspaceFactCommand(disappearing, command, send), /另一个标签页/);
  for (const raw of ["null", "[]", "not-json"]) {
    const store = storage(); store.setItem("joblens.workspaceFactCommand.workspace", raw);
    assert.throws(() => readWorkspaceFactCommand(store, "workspace"));
  }
  assert.equal(calls, 0);
});

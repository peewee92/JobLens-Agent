import assert from "node:assert/strict";
import test from "node:test";
import {readPendingExecution, sendAnalysisExecution, clearPendingExecution, type PendingAnalysisExecution} from "../lib/analysis-execution";
import {prioritizeApplicationActions} from "../lib/application-actions";
import type {ApplicationExecutionAction} from "../lib/contracts";

function storage() {
  const values = new Map<string, string>();
  return {getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => {values.set(key, value);}, removeItem: (key: string) => {values.delete(key);}};
}
const command: PendingAnalysisExecution = {version: 1, threadId: "thread", body: {commandId: "command", resultId: "saved", jobIds: ["job_1", "job_2"]}};

test("execution saves the exact command before sending; network retries use its original identity and scope", async () => {
  const saved = storage();
  const calls: string[] = [];
  const fetcher = (async (_url: unknown, init: RequestInit) => {
    assert.deepEqual(readPendingExecution(saved, "thread"), command);
    calls.push(init.body as string);
    if (calls.length === 1) throw new Error("connection lost after send");
    return new Response("{}", {status: 200});
  }) as typeof fetch;
  await assert.rejects(sendAnalysisExecution(saved, command, fetcher));
  await sendAnalysisExecution(saved, readPendingExecution(saved, "thread")!, fetcher);
  assert.equal(calls.length, 2);
  assert.equal(calls[0], calls[1]);
  clearPendingExecution(saved, command);
  assert.equal(readPendingExecution(saved, "thread"), null);
});

test("execution refuses to overwrite another unresolved command or send when local persistence fails", async () => {
  const saved = storage(); let calls = 0;
  const fetcher = (async () => {calls++; return new Response("{}");}) as typeof fetch;
  await sendAnalysisExecution(saved, command, fetcher);
  await assert.rejects(sendAnalysisExecution(saved, {...command, body: {...command.body, commandId: "other"}}, fetcher));
  assert.equal(calls, 1);
  const broken = {...storage(), setItem() {throw new Error("storage unavailable");}};
  await assert.rejects(sendAnalysisExecution(broken, command, fetcher));
  assert.equal(calls, 1);
});

test("a competing tab changing the journal before send prevents transmission", async () => {
  const saved = storage(); let calls = 0;
  const competing = {...saved, setItem(key: string, value: string) {
    saved.setItem(key, value.replace('"commandId":"command"', '"commandId":"newer"'));
  }};
  await assert.rejects(sendAnalysisExecution(competing, command, (async () => {calls++; return new Response("{}");}) as typeof fetch));
  assert.equal(calls, 0);
  clearPendingExecution(saved, command);
  assert.equal(readPendingExecution(saved, "thread")!.body.commandId, "newer");
});

test("action ordering exposes open evidence work before optional preparation, without mutating the source", () => {
  const action = (id: string, status: string, type: string) => ({actionId: id, status, actionType: type, createdAt: "2026-10-25T00:00:00Z"}) as ApplicationExecutionAction;
  const original = [action("resume", "todo", "improve_resume"), action("done", "done", "collect_evidence"),
    action("evidence", "todo", "collect_evidence"), action("active", "in_progress", "prepare_interview")];
  assert.deepEqual(prioritizeApplicationActions(original).map(a => a.actionId), ["active", "evidence", "resume", "done"]);
  assert.equal(original[0].actionId, "resume");
});

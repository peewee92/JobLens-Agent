import assert from "node:assert/strict";
import test from "node:test";
import {readModelConnection} from "../lib/model-connection-read";

const error = (status: number, code: string) => Response.json({error: {code}}, {status});
const noSession = () => error(410, "demo_session_expired");

test("a cold read recovers through one non-cached GET without creating a session", async () => {
  const checks: {path: string; method?: string}[] = [];
  const fetchStatus: typeof fetch = async (path, init) => {
    checks.push({path: String(path), method: init?.method});
    assert.equal(init?.cache, "no-store");
    return checks.length === 1 ? error(503, "backend_unavailable") : noSession();
  };
  assert.deepEqual(await readModelConnection(new AbortController().signal, fetchStatus, 0), {kind: "ready", status: null});
  assert.deepEqual(checks, Array.from({length: 2}, () => ({path: "/api/byok/model-connection", method: "GET"})));
});

test("an HTML startup page or network abort of a single GET can be followed by a valid read", async () => {
  const failures = [
    async () => new Response("<html>Starting</html>", {headers: {"Content-Type": "text/html"}}),
    async () => { throw new DOMException("Timed out", "TimeoutError"); },
  ];
  for (const fail of failures) {
    let calls = 0;
    const fetchStatus: typeof fetch = () => ++calls === 1 ? fail() : Promise.resolve(noSession());
    assert.deepEqual(await readModelConnection(new AbortController().signal, fetchStatus, 0), {kind: "ready", status: null});
    assert.equal(calls, 2);
  }
});

test("two temporary failures stop without reporting that a session is missing", async () => {
  let calls = 0;
  const fetchStatus: typeof fetch = async () => error(++calls === 1 ? 502 : 504, "backend_unavailable");
  assert.deepEqual(await readModelConnection(new AbortController().signal, fetchStatus, 0), {kind: "unavailable"});
  assert.equal(calls, 2);
});

test("a valid existing connection is returned unchanged without retry", async () => {
  const status = {connected: true, version: 2, seed: "sample", recentCalls: [],
    connection: {name: "test connection", baseUrl: "https://models.example.test/v1", model: "fixture", apiStyle: "responses"}};
  let calls = 0;
  const fetchStatus: typeof fetch = async () => { calls++; return Response.json(status); };
  assert.deepEqual(await readModelConnection(new AbortController().signal, fetchStatus, 0), {kind: "ready", status});
  assert.equal(calls, 1);
});

test("a sample session can start BYOK, but a closed gate or malformed JSON status is not ready", async () => {
  const fixtures = [
    {make: () => error(403, "demo_route_disabled"), result: {kind: "ready", status: null}},
    {make: () => error(403, "byok_disabled"), result: {kind: "unavailable"}},
    {make: () => Response.json({active: true}), result: {kind: "unavailable"}},
  ];
  for (const {make, result} of fixtures) {
    let calls = 0;
    const fetchStatus: typeof fetch = async () => { calls++; return make(); };
    assert.deepEqual(await readModelConnection(new AbortController().signal, fetchStatus, 0), result);
    assert.equal(calls, 1);
  }
});

test("leaving the page aborts the in-flight GET and prevents another check", async () => {
  const controller = new AbortController();
  let calls = 0;
  const fetchStatus: typeof fetch = (_path, init) => new Promise((_resolve, reject) => {
    calls++;
    const signal = init?.signal;
    assert.ok(signal);
    signal.addEventListener("abort", () => reject(signal.reason), {once: true});
  });
  const read = readModelConnection(controller.signal, fetchStatus, 0);
  controller.abort();
  assert.deepEqual(await read, {kind: "unavailable"});
  assert.equal(calls, 1);
});

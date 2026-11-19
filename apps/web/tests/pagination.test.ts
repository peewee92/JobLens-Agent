import {test} from "node:test";
import assert from "node:assert/strict";
import {lastPageOffset, pageWindow, parsePageOffset, readKnownPage} from "../lib/pagination";
import {userFacingReadError} from "../lib/user-facing-errors";

test("pagination separates actual totals from an unknown total", () => {
  assert.deepEqual(pageWindow(80, 20, 201), {current: 5, last: 11, numbers: [1, 4, 5, 6, 11]});
  assert.deepEqual(pageWindow(20, 20), {current: 2, last: undefined, numbers: []});
  assert.equal(lastPageOffset(41, 20), 40);
  assert.equal(lastPageOffset(40, 20), 20);
  assert.equal(lastPageOffset(0, 20), 0);
  assert.equal(parsePageOffset(["20", "100"]), 0);
  assert.equal(parsePageOffset("120"), 120);
});

test("an obsolete page may re-read the last page once, without retrying errors", async () => {
  const calls: number[] = [];
  assert.deepEqual(await readKnownPage(60, 20, async offset => {
    calls.push(offset);
    return {total: 23, items: offset === 20 ? [1, 2, 3] : []};
  }), {page: {total: 23, items: [1, 2, 3]}, offset: 20, adjusted: true});
  assert.deepEqual(calls, [60, 20]);
  await assert.rejects(readKnownPage(0, 20, async () => {throw new Error("unavailable");}), /unavailable/);
});

test("read errors don't pretend to know whether a write happened", () => {
  assert.match(userFacingReadError(504, "backend_read_timeout", "fallback"), /重新读取/);
  assert.match(userFacingReadError(403, undefined, "fallback"), /有权限/);
  assert.doesNotMatch(userFacingReadError(503, "backend_unavailable", "fallback"), /原请求/);
});

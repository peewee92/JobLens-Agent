import test from "node:test";
import assert from "node:assert/strict";
import {validatedRunLabels} from "../lib/agent-run-labels";
test("saved run labels preserve requested identities and ignore malformed or unrelated results", () => {
  assert.deepEqual(validatedRunLabels(["a", "b"], {items: [{id: "a", title: "工程师"}, {id: "b", title: ""}, {id: "c", title: "无关"}, null]}), {a: "工程师"});
  assert.deepEqual(validatedRunLabels(["a"], null), {});
});

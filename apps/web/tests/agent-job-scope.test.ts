import assert from "node:assert/strict";
import test from "node:test";
import {agentScopeFromProfile, agentScopeHref, initialAgentJobScope, jobDetailWithAgentScope, parseAgentScope, profileWithAgentScope} from "../lib/agent-job-scope";
test("an explicit historical job replaces the default selection", () => {
  assert.deepEqual(initialAgentJobScope(["other", "original"], "original"), ["original"]);
  assert.deepEqual(initialAgentJobScope(["other"], "missing"), []);
  assert.deepEqual(initialAgentJobScope(["a", "b"], undefined), ["a", "b"]);
});

test("profile return is restricted to a focus job within a valid batch", () => {
  const ids = ["a", "job/2"];
  const href = new URL(profileWithAgentScope("job/2", ids), "https://example.test");
  assert.equal(href.pathname, "/profile");
  assert.deepEqual(agentScopeFromProfile(href.searchParams.get("scopeFocusJobId")!, href.searchParams.getAll("scopeJobId")), {jobId: "job/2", ids});
  assert.equal(agentScopeFromProfile("other", ids), null);
  assert.equal(agentScopeFromProfile(["a", "b"], ids), null);
  assert.equal(agentScopeFromProfile("a", ["a", "a"]), null);
  assert.equal(agentScopeFromProfile("https://example.org", ids), null);
});

test("a returned batch is preserved exactly or fails closed", () => {
  assert.deepEqual(initialAgentJobScope(["a", "b", "other"], ["b", "a"]), ["b", "a"]);
  assert.deepEqual(initialAgentJobScope(["a"], ["a", "missing"]), []);
  assert.deepEqual(parseAgentScope(["a", "b"]), ["a", "b"]);
  for (const bad of [[], ["a", "a"], [""], [" ".repeat(2)], ["a".repeat(101)], Array.from({length: 51}, (_, i) => `${i}`)]) assert.equal(parseAgentScope(bad), null);
});

test("roundtrip uses only local paths and preserves encoded job ids", () => {
  const ids = ["job 1", "job/2"];
  const detail = new URL(jobDetailWithAgentScope(ids[1], ids), "https://example.test");
  assert.equal(detail.pathname, "/jobs/job%2F2");
  assert.deepEqual(detail.searchParams.getAll("scopeJobId"), ids);
  const back = new URL(agentScopeHref(ids), "https://example.test");
  assert.equal(back.pathname, "/agent");
  assert.deepEqual(back.searchParams.getAll("scopeJobId"), ids);
  assert.equal(new URL(agentScopeHref(["https://evil.test/"]), "https://example.test").origin, "https://example.test");
});

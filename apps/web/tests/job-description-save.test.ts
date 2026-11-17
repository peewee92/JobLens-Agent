import assert from "node:assert/strict";
import test from "node:test";
import {confirmedDescriptionHref, descriptionSavedQuery, isDescriptionRevision} from "../lib/job-description-save";

test("successful correction reloads the same posting without dropping the selected batch", () => {
  const revision = "a".repeat(64);
  const before = new URL("https://example.test/jobs/job_1?scopeJobId=job_1&scopeJobId=job_2#job-match");
  const after = new URL(confirmedDescriptionHref(before, revision), before.origin);
  assert.equal(after.pathname, before.pathname);
  assert.deepEqual(after.searchParams.getAll("scopeJobId"), ["job_1", "job_2"]);
  assert.equal(after.searchParams.get(descriptionSavedQuery), revision);
  assert.equal(after.hash, "#job-description");
  assert.equal(isDescriptionRevision(revision), true);
  assert.equal(isDescriptionRevision(["a".repeat(64)]), false);
  assert.equal(isDescriptionRevision("1"), false);
});

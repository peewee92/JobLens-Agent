import assert from "node:assert/strict";
import test from "node:test";

import {requirementExtractionOutcome} from "../lib/requirement-extraction-outcome";

const errorBody = (code: string) => ({error: {code, message: "private internal validation details"}});
const jobId = "job-1";

test("known offline rejections are safe to explicitly retry, without echoing raw errors", () => {
  for (const [status, code] of [
    [502, "invalid_requirement_extractor_output"],
    [502, "requirement_extractor_failed"],
    [503, "requirement_extractor_unavailable"],
  ] as const) {
    const result = requirementExtractionOutcome(status, errorBody(code), jobId);
    assert.equal(result.kind, "rejected");
    assert.match(result.message, /没有保存结果/);
    assert.doesNotMatch(result.message, /private|validation/);
  }
});

test("ambiguous errors and incomplete success require checking saved results first", () => {
  for (const [status, body] of [
    [408, null], [500, null], [502, "<html>Gateway</html>"], [503, errorBody("backend_unavailable")],
    [504, errorBody("invalid_requirement_extractor_output")],
    [201, {}], [201, {jobId: "another-job", extractionId: "req-1", requirements: []}],
  ] as const) {
    assert.deepEqual(requirementExtractionOutcome(status, body, jobId), {kind: "uncertain"});
  }
});
test("success requires a usable extraction for the requested job; 4xx rejections remain explicit", () => {
  assert.deepEqual(requirementExtractionOutcome(201, {jobId, extractionId: "req-1", requirements: [{}]}, jobId), {kind: "saved"});
  const blocked = requirementExtractionOutcome(409, errorBody("requirement_model_authorization_required"), jobId);
  assert.equal(blocked.kind, "rejected");
  assert.match(blocked.message, /授权/);
});

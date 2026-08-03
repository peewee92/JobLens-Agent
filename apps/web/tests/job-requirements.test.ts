import assert from "node:assert/strict";
import test from "node:test";

import type {JobRequirement} from "@/lib/contracts";
import {
  requirementImportanceLabel,
  requirementTypeLabel,
  sortJobRequirements,
} from "@/lib/job-requirements";

function requirement(
  id: string,
  importance: JobRequirement["importance"],
  index: number,
): JobRequirement {
  return {
    id,
    jobId: "job_test",
    extractionId: "reqrun_test",
    requirementIndex: index,
    type: "skill",
    originalText: id,
    normalizedCapability: id,
    importance,
    evidenceSpan: id,
    confidence: 0.9,
    extractorVersion: "requirement-extractor-v1",
  };
}

test("Requirement labels preserve type and importance semantics", () => {
  assert.equal(requirementTypeLabel("responsibility"), "职责");
  assert.equal(requirementTypeLabel("constraint"), "约束");
  assert.equal(requirementImportanceLabel("must_have"), "必须");
  assert.equal(requirementImportanceLabel("preferred"), "优先");
  assert.equal(requirementImportanceLabel("bonus"), "加分");
});

test("must-have Requirements sort before preferred and bonus without mutation", () => {
  const input = [
    requirement("bonus", "bonus", 0),
    requirement("preferred", "preferred", 1),
    requirement("must", "must_have", 2),
  ];

  const sorted = sortJobRequirements(input);

  assert.deepEqual(sorted.map((item) => item.id), ["must", "preferred", "bonus"]);
  assert.deepEqual(input.map((item) => item.id), ["bonus", "preferred", "must"]);
});

import assert from "node:assert/strict";
import test from "node:test";

import type {JobRequirement, JobRequirementReleaseReadiness} from "@/lib/contracts";
import {
  requirementImportanceLabel,
  requirementReleaseBlockerLabels,
  requirementReleaseLabel,
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

test("Requirement release labels distinguish allowed facts from blockers", () => {
  const base: JobRequirementReleaseReadiness = {
    jobId: "job_test",
    releaseEligible: true,
    currentDescriptionSha256: "a".repeat(64),
    extractionId: "reqrun_test",
    extractionInputHash: "a".repeat(64),
    provider: "openai",
    model: "quality-model",
    extractorVersion: "requirement-extractor-v1",
    promptVersion: "requirement-extraction-v1",
    traceRunId: "run_test",
    requirementCount: 1,
    acceptedBaselineBatchId: "reqreviewbatch_test",
    acceptedBaselineDecisionId: "reqbatchdecision_test",
    acceptedBaselineEvidenceFingerprint: "b".repeat(64),
    blockers: [],
  };

  assert.equal(requirementReleaseLabel(base), "已通过 Requirement 事实发布门禁");
  assert.match(
    requirementReleaseLabel({
      ...base,
      releaseEligible: false,
      blockers: [{code: "extraction_input_stale", message: "stale"}],
    }),
    /1 个阻塞项/,
  );
  assert.equal(
    requirementReleaseBlockerLabels.extraction_input_stale,
    "Extraction 已不对应当前 JD",
  );
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

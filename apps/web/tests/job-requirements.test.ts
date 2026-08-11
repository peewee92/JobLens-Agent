import assert from "node:assert/strict";
import test from "node:test";

import type {JobRequirement, JobRequirementReleaseReadiness} from "@/lib/contracts";
import {
  requirementImportanceLabel,
  requirementReleaseBlockerCopy,
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

  assert.equal(requirementReleaseLabel(base), "岗位要求已准备好，可用于后续匹配");
  assert.equal(
    requirementReleaseLabel({
      ...base,
      releaseEligible: false,
      blockers: [{code: "extraction_input_stale", message: "stale"}],
    }),
    "岗位要求还在准备中，暂时不会用于匹配",
  );
  assert.deepEqual(requirementReleaseBlockerCopy("accepted_baseline_missing"), {
    title: "项目级 AI 质量验收还未完成",
    description:
      "这不是当前岗位漏做了某一步。系统还没有形成经过人工接受的 Requirement 分析基线；你仍然可以先分析这个岗位，但正式匹配会继续保持锁定。",
  });
  assert.deepEqual(requirementReleaseBlockerCopy("requirement_extraction_missing"), {
    title: "这个岗位还没有完成要求分析",
    description:
      "点击“分析岗位要求”，系统会从岗位描述中整理学历、经验、技能和职责等关键要求。",
  });
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

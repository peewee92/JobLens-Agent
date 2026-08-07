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
    title: "系统还在确认 AI 分析是否足够可靠",
    description:
      "在用于岗位匹配前，我们会先人工抽查 AI 对岗位要求的理解，避免错误分析影响推荐结果。",
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

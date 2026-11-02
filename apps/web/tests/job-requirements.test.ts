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
    title: "当前没有有效的岗位要求审核基线",
    description:
      "可能尚未建立审核基线，也可能原有基线已失效。仅重新分析当前岗位不能保证恢复匹配；请查看人工审核状态，或联系维护人员处理。",
  });
  assert.match(requirementReleaseBlockerCopy("extraction_cohort_mismatch").description, /不保证解除阻断/);
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

test("short or missing descriptions give a repair step instead of an unavailable analysis action", async () => {
  const {hasEnoughJobDescription, requirementReleaseBlockerCopy, shortJobDescriptionGuidance} = await import("../lib/job-requirements");
  assert.equal(hasEnoughJobDescription(" short "), false);
  assert.equal(hasEnoughJobDescription("x".repeat(40)), true);
  assert.equal(requirementReleaseBlockerCopy("requirement_extraction_missing", null).description, shortJobDescriptionGuidance);
  assert.match(requirementReleaseBlockerCopy("requirement_extraction_missing", "x".repeat(40)).description, /点击/);
  assert.match(requirementReleaseBlockerCopy("requirement_extraction_missing").description, /点击/);
});

test("description length follows the backend's Unicode code point limits", async () => {
  const {hasEnoughJobDescription, jobDescriptionIssue, requirementReleaseBlockerCopy, longJobDescriptionGuidance} = await import("../lib/job-requirements");
  assert.equal(hasEnoughJobDescription("😀".repeat(39)), false);
  assert.equal(hasEnoughJobDescription("😀".repeat(40)), true);
  assert.equal(hasEnoughJobDescription("字".repeat(50_000)), true);
  assert.equal(hasEnoughJobDescription("字".repeat(50_001)), false);
  assert.equal(jobDescriptionIssue("字".repeat(50_001)), longJobDescriptionGuidance);
  assert.equal(requirementReleaseBlockerCopy("extraction_input_stale", "字".repeat(50_001)).description, longJobDescriptionGuidance);
  assert.match(requirementReleaseBlockerCopy("extraction_input_stale", "x".repeat(40)).description, /重新分析/);
  assert.match(requirementReleaseBlockerCopy("extraction_input_stale").description, /重新分析/);
});

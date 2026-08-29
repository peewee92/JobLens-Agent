import assert from "node:assert/strict";
import test from "node:test";

import {
  evidenceRenameImpacts,
  focusedSkillEvidenceIssue,
  migrateEvidenceKeyReferences,
  repairFocusedSkillEvidenceKeys,
} from "../lib/profile-draft-integrity";

test("evidence rename preview lists only skills that already reference the old key", () => {
  const impacts = evidenceRenameImpacts({
    originalEvidenceKeys: ["project-old", "work-a"],
    evidence: [
      {key: "project-renamed", summary: "Built a production feature."},
      {key: "work-a", summary: "Worked on platform delivery."},
    ],
    skills: [
      {name: "React", evidenceKeys: ["project-old", "work-a"]},
      {name: "TypeScript", evidenceKeys: ["PROJECT-OLD"]},
      {name: "Python", evidenceKeys: ["work-a"]},
    ],
  });

  assert.deepEqual(impacts, [{
    evidenceIndex: 0,
    previousKey: "project-old",
    nextKey: "project-renamed",
    affectedSkillNames: ["React", "TypeScript"],
  }]);
});

test("evidence rename preview ignores new evidence and cosmetic key changes", () => {
  const impacts = evidenceRenameImpacts({
    originalEvidenceKeys: ["Project-A"],
    evidence: [
      {key: " project-a ", summary: "Same evidence."},
      {key: "brand-new", summary: "New evidence."},
    ],
    skills: [{name: "React", evidenceKeys: ["Project-A"]}],
  });

  assert.deepEqual(impacts, []);
});

test("evidence key migration changes only existing references and deduplicates the target", () => {
  const migrated = migrateEvidenceKeyReferences({
    currentEvidenceKeys: ["project-old", "work-a", "PROJECT-RENAMED"],
    previousEvidenceKey: "project-old",
    nextEvidenceKey: "project-renamed",
  });

  assert.deepEqual(migrated, ["project-renamed", "work-a"]);
});

test("focused skill remains valid when its linked evidence is still complete", () => {
  const issue = focusedSkillEvidenceIssue({
    focusCapability: "React",
    evidence: [{key: "project-a", summary: "Built a React desktop workflow."}],
    skills: [{name: "React", evidenceKeys: ["project-a"]}],
  });

  assert.equal(issue, null);
});

test("focused skill reports a dangling link when an evidence key was renamed", () => {
  const issue = focusedSkillEvidenceIssue({
    focusCapability: "React",
    evidence: [{key: "project-renamed", summary: "Built a React desktop workflow."}],
    skills: [{name: "React", evidenceKeys: ["project-a"]}],
  });

  assert.deepEqual(issue, {
    kind: "dangling_links",
    skillName: "React",
    missingEvidenceKeys: ["project-a"],
  });
});

test("focused skill reports missing support when all evidence links were removed", () => {
  const issue = focusedSkillEvidenceIssue({
    focusCapability: "React",
    evidence: [{key: "project-a", summary: "Built a React desktop workflow."}],
    skills: [{name: "React", evidenceKeys: []}],
  });

  assert.deepEqual(issue, {kind: "missing_links", skillName: "React"});
});

test("unrelated skills do not block the current evidence action", () => {
  const issue = focusedSkillEvidenceIssue({
    focusCapability: "React",
    evidence: [{key: "project-a", summary: "Built a React desktop workflow."}],
    skills: [{name: "TypeScript", evidenceKeys: []}],
  });

  assert.equal(issue, null);
});

test("an empty evidence summary does not count as direct support", () => {
  const issue = focusedSkillEvidenceIssue({
    focusCapability: "React",
    evidence: [{key: "project-a", summary: "   "}],
    skills: [{name: "React", evidenceKeys: ["project-a"]}],
  });

  assert.deepEqual(issue, {
    kind: "dangling_links",
    skillName: "React",
    missingEvidenceKeys: ["project-a"],
  });
});

test("repair replaces only confirmed dangling links and preserves valid evidence", () => {
  const repaired = repairFocusedSkillEvidenceKeys({
    currentEvidenceKeys: ["project-old", "work-still-valid"],
    missingEvidenceKeys: ["project-old"],
    replacementEvidenceKey: "project-renamed",
  });

  assert.deepEqual(repaired, ["work-still-valid", "project-renamed"]);
});

test("repair can attach current evidence when the focused skill has no links", () => {
  const repaired = repairFocusedSkillEvidenceKeys({
    currentEvidenceKeys: [],
    missingEvidenceKeys: [],
    replacementEvidenceKey: "project-a",
  });

  assert.deepEqual(repaired, ["project-a"]);
});

test("repair does not duplicate an already linked replacement", () => {
  const repaired = repairFocusedSkillEvidenceKeys({
    currentEvidenceKeys: ["Project-A", "project-old"],
    missingEvidenceKeys: ["project-old"],
    replacementEvidenceKey: "project-a",
  });

  assert.deepEqual(repaired, ["Project-A"]);
});

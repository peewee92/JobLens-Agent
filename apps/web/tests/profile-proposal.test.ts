import assert from "node:assert/strict";
import test from "node:test";

import type {ProfileExtractionProposal} from "../lib/contracts";
import {proposalToProfileDraft} from "../lib/profile-proposal";

const proposal: ProfileExtractionProposal = {
  runId: "run_test",
  extractorVersion: "profile-extractor-v1",
  model: "fixture-profile-extractor",
  promptVersion: "profile-proposal-v1",
  headline: "8 年前端工程师",
  yearsOfExperience: 8,
  evidence: [
    {
      key: "work-1",
      type: "work",
      summary: "负责 React 平台开发",
      source: "resume",
      evidenceSpan: "负责 React 平台开发",
    },
  ],
  skills: [
    {
      name: "React",
      level: "strong",
      evidenceKeys: ["work-1"],
    },
  ],
  warnings: [],
};

test("proposalToProfileDraft preserves evidence links and trace provenance", () => {
  const draft = proposalToProfileDraft(proposal);

  assert.equal(draft.headline, proposal.headline);
  assert.equal(draft.years, "8");
  assert.deepEqual(draft.evidence, [
    {
      key: "work-1",
      type: "work",
      summary: "负责 React 平台开发",
      source: "resume proposal run_test",
    },
  ]);
  assert.deepEqual(draft.skills, [
    {
      name: "React",
      level: "strong",
      evidenceKeys: ["work-1"],
    },
  ]);
});

test("proposalToProfileDraft does not mutate provider arrays", () => {
  const draft = proposalToProfileDraft(proposal);

  draft.skills[0].evidenceKeys.push("other");

  assert.deepEqual(proposal.skills[0].evidenceKeys, ["work-1"]);
});

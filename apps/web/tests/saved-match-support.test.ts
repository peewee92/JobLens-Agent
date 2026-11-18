import assert from "node:assert/strict";
import test from "node:test";

import type {JobMatchReport, SavedCareerAnalysis} from "../lib/contracts";
import {savedMatchSupport} from "../lib/saved-match-support";

const saved = {
  profileId: "profile", profileVersion: 2, searchIntentId: "intent", searchIntentVersion: 1, selectedJobIds: ["job"],
} as SavedCareerAnalysis;
const binding = {jobId: "job", extractionId: "extract", matchReportId: "report", policyVersion: "policy", title: "", company: ""};
const report = {
  jobId: "job", extractionId: "extract", profileId: "profile", profileVersion: 2, searchIntentId: "intent",
  searchIntentVersion: 1, policyVersion: "policy", requirementResults: [
    {requirementId: "partial", assessmentSource: "provider", semanticVerdict: "partial", evidenceIds: ["ev"]},
    {requirementId: "exact", assessmentSource: "provider", semanticVerdict: "matched", evidenceIds: ["ev"]},
    {requirementId: "unknown", assessmentSource: "provider", semanticVerdict: "partial", evidenceIds: []},
    {requirementId: "gate", assessmentSource: "deterministic", semanticVerdict: "partial", evidenceIds: ["ev"]},
  ],
} as JobMatchReport;
const historical = {reportId: "report", createdAt: "", isCurrent: false, staleReasons: [], report};

test("saved preparation reads evidence-backed partial support from the exact historical report", () => {
  const current = {...historical, reportId: "latest", isCurrent: true, report: {...report, requirementResults: []}};
  assert.deepEqual(savedMatchSupport(saved, binding, {items: [current, historical], count: 2}), ["partial"]);
  assert.deepEqual(savedMatchSupport(saved, binding, {items: [current], count: 1}), []);
});

test("saved preparation never borrows support if any source binding differs", () => {
  for (const override of [
    {extractionId: "another"}, {jobId: "another"}, {profileId: "another"}, {profileVersion: 3},
    {searchIntentId: "another"}, {searchIntentVersion: 2}, {policyVersion: undefined},
  ]) {
    const changed = {...historical, report: {...report, ...override}};
    assert.deepEqual(savedMatchSupport(saved, binding, {items: [changed], count: 1}), []);
  }
  assert.deepEqual(savedMatchSupport({...saved, selectedJobIds: []}, binding, {items: [historical], count: 1}), []);
});

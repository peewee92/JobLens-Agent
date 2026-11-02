import test from "node:test";
import assert from "node:assert/strict";
import {classifyImportMatchReadiness, importedUniqueJobIds, validImportMatchInputs, type ImportMatchInputs} from "../lib/import-match-readiness";

test("use the embedded match gate and reject incomplete or mismatched responses", () => {
  const value = {jobId: "a", inputsReleaseEligible: true, jobRequirements: {jobId: "a", releaseEligible: true, blockers: []}} as unknown as ImportMatchInputs;
  assert.equal(validImportMatchInputs("a", value), true);
  assert.equal(validImportMatchInputs("b", value), false);
  assert.equal(validImportMatchInputs("a", {...value, jobRequirements: {...value.jobRequirements, jobId: "b"}}), false);
  assert.equal(validImportMatchInputs("a", {...value, jobRequirements: undefined} as unknown as ImportMatchInputs), false);
});

test("each imported job uses its own readiness, including jobs beyond the review sample", () => {
  const items = Array.from({length: 51}, (_, index) => classifyImportMatchReadiness({
    rankingAvailable: true, ranked: index === 0, matchInputsReady: index !== 22, requirementsReady: index !== 22,
  }));
  assert.equal(items[0], "matched");
  assert.equal(items[22], "requirements_blocked");
  assert.equal(items[50], "ready");
  assert.equal(items.filter(x => x === "ready").length, 49);
});

test("failed reads, incomplete career facts and unavailable ranking are not treated as ready", () => {
  assert.equal(classifyImportMatchReadiness({rankingAvailable: false, ranked: false, matchInputsReady: true, requirementsReady: true}), "unknown");
  assert.equal(classifyImportMatchReadiness({rankingAvailable: true, ranked: false, matchInputsReady: null, requirementsReady: true}), "unknown");
  assert.equal(classifyImportMatchReadiness({rankingAvailable: true, ranked: false, matchInputsReady: false, requirementsReady: true}), "unknown");
  assert.equal(classifyImportMatchReadiness({rankingAvailable: true, ranked: false, matchInputsReady: null, requirementsReady: false}), "requirements_blocked");
});

test("conflicting or missing separate reads cannot certify a matched report or ready input", () => {
  const base = {rankingAvailable: true, ranked: true, matchInputsReady: true, requirementsReady: true};
  assert.equal(classifyImportMatchReadiness({...base, requirementsReady: false}), "unknown");
  assert.equal(classifyImportMatchReadiness({...base, requirementsReady: null}), "unknown");
  assert.equal(classifyImportMatchReadiness({...base, matchInputsReady: false}), "unknown");
  assert.equal(classifyImportMatchReadiness({...base, matchInputsReady: null}), "unknown");
  assert.equal(classifyImportMatchReadiness({...base, ranked: false, requirementsReady: false}), "unknown");
  assert.equal(classifyImportMatchReadiness({...base, ranked: false, requirementsReady: null}), "unknown");
});

test("user-marked jobs do not enter matching and unknown flags fail closed", () => {
  const base = {rankingAvailable: true, ranked: false, matchInputsReady: true, requirementsReady: true};
  assert.equal(classifyImportMatchReadiness({...base, userMarkedInactive: true}), "inactive");
  assert.equal(classifyImportMatchReadiness({...base, userMarkedInactive: null}), "unknown");
  assert.equal(classifyImportMatchReadiness({...base, userMarkedInactive: false}), "ready");
});

test("import observations preserve order but processing counts each actual job only once", () => {
  const items = [{jobId:"a"}, {jobId:"a"}, {jobId:null}, {jobId:"b"}, {jobId:"a"}];
  assert.deepEqual(importedUniqueJobIds(items), ["a", "b"]);
  assert.equal(items.length, 5);
  assert.deepEqual(importedUniqueJobIds([{jobId:null}]), []);
});

import assert from "node:assert/strict";
import test from "node:test";
import {completionCriterionLabel, currentStateLabel, gapImportanceLabel, gapNextStep} from "../lib/gap-language";

test("missing proof is never a verdict that the user lacks ability", () => {
  assert.match(currentStateLabel("missing"), /没有确认/);
  assert.match(currentStateLabel("skill_exists_without_confirmed_evidence"), /写过.*缺少.*证据/);
  assert.doesNotMatch(currentStateLabel("new-internal-code"), /new-internal-code/);
  assert.doesNotMatch(completionCriterionLabel("new-internal-code"), /new-internal-code/);
});
test("importance comes from requirement facts, not priority or an invented default", () => {
  assert.match(gapImportanceLabel(1, [], new Map()), /必需/);
  assert.match(gapImportanceLabel(0, ["r"], new Map([["r", "bonus"]])), /加分项.*可选/);
  assert.match(gapImportanceLabel(undefined, [], new Map()), /未确认/);
  assert.match(gapNextStep(0), /不必.*推迟投递/);
  assert.match(gapNextStep(1), /是否做过.*如实/);
  assert.match(gapNextStep(undefined), /先看岗位原文/);
});

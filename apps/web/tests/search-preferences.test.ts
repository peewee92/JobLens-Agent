import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
import test from "node:test";
import {createElement} from "react";
import {renderToStaticMarkup} from "react-dom/server";
import {PreferenceCheckList} from "../components/preference-check-list";
import type {PreferenceCheck} from "../lib/contracts";

test("shared preference example renders uncertainty without claiming a conflict", async () => {
  const check = JSON.parse(await readFile(new URL("../../../packages/contracts/examples/preference-check.example.json", import.meta.url), "utf8")) as PreferenceCheck;
  const html = renderToStaticMarkup(createElement(PreferenceCheckList, {checks: [check], version: 3}));
  assert.match(html, /0 项明确冲突，1 项待核实/);
  assert.match(html, /岗位月薪 15–25K/);
  assert.match(html, /意向版本 3/);
  assert.match(html, /href="\/profile#search-intent"/);
  assert.doesNotMatch(html, /open=""/);
});

test("explicit conflict is expanded while preserving the actionable reason", () => {
  const check: PreferenceCheck = {key: "salary", status: "missing", code: "salary_conflict",
    reason: "岗位上限低于已确认底线", intentFields: ["minimumSalaryK"], jobFields: ["salaryMaxK"]};
  const html = renderToStaticMarkup(createElement(PreferenceCheckList, {checks: [check], version: 2}));
  assert.match(html, /1 项明确冲突，0 项待核实/);
  assert.match(html, /open=""/);
  assert.match(html, /岗位上限低于已确认底线/);
  assert.equal(renderToStaticMarkup(createElement(PreferenceCheckList, {checks: []})), "");
});

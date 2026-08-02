import assert from "node:assert/strict";
import test from "node:test";

import {
  formatImportOutcome,
  formatRemoteStatus,
  formatSalary,
} from "@/lib/format";

test("formatSalary covers complete and partial ranges", () => {
  assert.equal(formatSalary(15, 30), "15–30K");
  assert.equal(formatSalary(20, null), "≥ 20K");
  assert.equal(formatSalary(null, 25), "≤ 25K");
  assert.equal(formatSalary(null, null), "薪资未公开");
});

test("public labels preserve three-state remote semantics", () => {
  assert.equal(formatRemoteStatus("confirmed"), "明确支持远程");
  assert.equal(formatRemoteStatus("rejected"), "明确不支持远程");
  assert.equal(formatRemoteStatus("unknown"), "远程信息不足");
});

test("import outcomes remain distinct", () => {
  assert.equal(formatImportOutcome("created"), "新建");
  assert.equal(formatImportOutcome("updated"), "更新");
  assert.equal(formatImportOutcome("skipped"), "跳过");
  assert.equal(formatImportOutcome("error"), "错误");
});

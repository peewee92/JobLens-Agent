import assert from "node:assert/strict";
import test from "node:test";

import {
  formatImportOutcome,
  formatRemoteStatus,
  formatSalary,
  jobSourceLabels,
} from "@/lib/format";

test("formatSalary covers complete and partial ranges", () => {
  assert.equal(formatSalary(15, 30), "15–30K");
  assert.equal(formatSalary(20, null), "≥ 20K");
  assert.equal(formatSalary(null, 25), "≤ 25K");
  assert.equal(formatSalary(null, null), "薪资未公开");
});

test("public labels preserve three-state remote semantics", () => {
  assert.equal(formatRemoteStatus("confirmed"), "支持远程");
  assert.equal(formatRemoteStatus("rejected"), "不支持远程");
  assert.equal(formatRemoteStatus("unknown"), "未说明是否远程");
});

test("import outcomes remain distinct", () => {
  assert.equal(formatImportOutcome("created"), "已添加");
  assert.equal(formatImportOutcome("updated"), "已更新");
  assert.equal(formatImportOutcome("skipped"), "未添加");
  assert.equal(formatImportOutcome("error"), "处理失败");
});

test("distinguishes a pasted job's save time from a collected job's source time", () => {
  assert.deepEqual(jobSourceLabels("manual"), {source: "手动粘贴", recordedAt: "保存时间"});
  assert.deepEqual(jobSourceLabels("example"), {source: "example", recordedAt: "采集时间"});
});

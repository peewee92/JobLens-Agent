import assert from "node:assert/strict";
import test from "node:test";
import {manualJobValidation, parsePastedJobs} from "../lib/manual-job-import";

test("numbered, copied job list keeps the original internal lines", () => {
  const jobs = parsePastedJobs("【样本｜非真实招聘】\r\n\r\n1. 甲｜公司甲\r\n要求：了解 Python。\r\n表格列一 | 表格列二\r\n  保留缩进\r\n\r\n2、乙 | 公司乙\r\n待补充");
  assert.deepEqual(jobs, [
    {title: "甲", company: "公司甲", description: "要求：了解 Python。\n表格列一 | 表格列二\n  保留缩进"},
    {title: "乙", company: "公司乙", description: "待补充"},
  ]);
  assert.equal(manualJobValidation(jobs[1]), null);
});
test("don't silently skip unrecognized leading text or accept more than twenty entries", () => {
  assert.throws(() => parsePastedJobs("仅一段招聘原文\n"));
  assert.throws(() => parsePastedJobs("岗位｜公司\n要求\n\n".repeat(21)), /20 条/);
  assert.match(manualJobValidation(parsePastedJobs("岗位｜公司")[0]) ?? "", /粘贴一段/);
});

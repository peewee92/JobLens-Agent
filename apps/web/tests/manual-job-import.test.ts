import assert from "node:assert/strict";
import test from "node:test";
import {duplicatePastedJobIndices, isUnlistedPastedCompany, manualJobValidation, parsePastedJobs} from "../lib/manual-job-import";

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

test("accepts a title-only list with explicit dividers, including blank paragraphs and optional company", () => {
  assert.deepEqual(parsePastedJobs("【合成样本】\n\n甲\n第一段\n\n第二段\n\n---\n乙｜公司乙\n待补充"), [
    {title: "甲", company: "公司未公开", description: "第一段\n\n第二段"},
    {title: "乙", company: "公司乙", description: "待补充"},
  ]);
  assert.throws(() => parsePastedJobs("甲\n要求\n---\n---\n乙\n描述"), /第 2 条/);
  assert.throws(() => parsePastedJobs(Array(21).fill("甲\n要求").join("\n---\n")), /20 条/);
  const [legacy] = parsePastedJobs("甲｜乙\n要求\n---\n这是正文\n\n丙｜丁\n另一条", {dividersAreDescription: true});
  assert.equal(legacy.description, "要求\n---\n这是正文");
});

test("exact duplicate hints distinguish different text, preserving the backend content identity", () => {
  const jobs = parsePastedJobs("甲\n原文\n---\n甲\n原文\n---\n甲\n另一份正文\n---\n甲｜公司乙\n原文");
  assert.deepEqual([...duplicatePastedJobIndices(jobs)], [1]);
});

test("explicit dividers never absorb a company-less posting into a named company's description", () => {
  const first = "甲｜公司甲\n第一条原文";
  const jobs = parsePastedJobs([first, "乙\n第二条原文", "丙\n待补充", first].join("\n\n---\n\n"));
  assert.deepEqual(jobs.map(job => [job.title, job.company, job.description]), [
    ["甲", "公司甲", "第一条原文"], ["乙", "公司未公开", "第二条原文"],
    ["丙", "公司未公开", "待补充"], ["甲", "公司甲", "第一条原文"],
  ]);
  assert.deepEqual([...duplicatePastedJobIndices(jobs)], [3]);
});

test("company-less postings are visibly unverified but not rejected by the importer", () => {
  const [missing, named] = parsePastedJobs("甲\n岗位原文\n---\n乙｜真实公司\n岗位原文");
  assert.ok(isUnlistedPastedCompany(missing.company));
  assert.equal(isUnlistedPastedCompany(named.company), false);
  assert.equal(manualJobValidation(missing), null);
});

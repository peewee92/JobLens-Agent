import assert from "node:assert/strict";
import test from "node:test";
import {existingMatchReportCopy, rankingOmissionMessage, rankingPreflight, rankingRecoveryAnchor, rankingScope} from "../lib/agent-ranking-preflight";

test("partial and empty rankings keep the requested scope visible", () => {
  const missing = {jobId: "a", reason: "report_missing", staleReasons: []};
  assert.deepEqual(rankingPreflight(["a", "b"], {items: [{jobId: "b", targetCandidate: true}], omissions: [missing]}), {scope: rankingScope(["a", "b"]), ranked: ["b"], candidates: ["b"], insufficient: [], omissions: [missing]});
  assert.deepEqual(rankingPreflight(["a"], {items: [], omissions: [missing]}).omissions, [missing]);
});
test("a readable report without a supported target is not a proposal", () => {
  const result = rankingPreflight(["a", "b"], {items: [{jobId: "a", targetCandidate: false}, {jobId: "b", targetCandidate: true}], omissions: []});
  assert.deepEqual(result.ranked, ["a", "b"]);
  assert.deepEqual(result.candidates, ["b"]);
  assert.deepEqual(result.insufficient, ["a"]);
  assert.deepEqual(rankingPreflight(["a"], {items: [{jobId: "a", targetCandidate: false}], omissions: []}).candidates, []);
});
test("selection order is irrelevant but scope changes invalidate the check", () => {
  assert.equal(rankingScope(["a", "b"]), rankingScope(["b", "a"]));
  assert.notEqual(rankingScope(["a", "b"]), rankingScope(["a"]));
});
test("malformed or unexpected ranking results do not enable a run", () => {
  for (const response of [null, {}, {items: [null], omissions: []}, {items: [{jobId: "a"}], omissions: []}, {items: [{jobId: "other", targetCandidate: true}], omissions: []}, {items: [{jobId: "a", targetCandidate: true}, {jobId: "a", targetCandidate: false}], omissions: []}, {items: [], omissions: []}, {items: [], omissions: [{jobId: "a", reason: "report_stale", staleReasons: []}]}]) {
    assert.throws(() => rankingPreflight(["a"], response));
  }
  assert.throws(() => rankingPreflight([], {items: []}));
  assert.throws(() => rankingPreflight(["a", "a"], {items: []}));
});

test("omissions explain different steps; new or absent recovery codes remain optional", () => {
  for (const [code, guidance] of [
    ["description_incomplete", /描述信息不足/],
    ["requirement_analysis_failed", /没有保存岗位要求/],
    ["requirements_not_analyzed", /先在岗位详情分析要求/],
    ["requirements_need_review", /不能用于匹配/],
    [null, /尚无匹配报告/],
    ["future_code", /尚无匹配报告/],
    ["constructor", /尚无匹配报告/],
  ] as const) {
    const result = rankingPreflight(["a"], {items: [], omissions: [
      {jobId: "a", reason: "report_missing", staleReasons: [], recoveryCode: code},
    ]});
    assert.match(rankingOmissionMessage(result.omissions[0]), guidance);
  }
  assert.match(rankingOmissionMessage({jobId: "a", reason: "report_stale", staleReasons: ["profile_changed"]}), /已过期.*职业资料已更新/);
  assert.match(rankingOmissionMessage({jobId: "a", reason: "hard_conflict", staleReasons: []}), /硬性条件冲突/);
});

test("a duplicate receipt explains the current report, not the pasted description", () => {
  const check = rankingPreflight(["current", "conflict", "historic", "missing"], {
    items: [{jobId: "current", targetCandidate: false}],
    omissions: [
      {jobId: "conflict", reason: "hard_conflict", staleReasons: []},
      {jobId: "historic", reason: "report_stale", staleReasons: ["job_description_changed"]},
      {jobId: "missing", reason: "report_missing", staleReasons: [], recoveryCode: "description_incomplete"},
    ],
  });
  assert.match(existingMatchReportCopy(check, "current"), /仍可用于当前比较/);
  assert.match(existingMatchReportCopy(check, "conflict"), /硬性条件冲突，不进入默认比较/);
  assert.match(existingMatchReportCopy(check, "historic"), /仅供历史查看/);
  assert.match(existingMatchReportCopy(check, "missing"), /描述信息不足.*补充完整原文/);
  assert.match(existingMatchReportCopy(check, "unknown"), /暂时无法核对/);
});

test("recovery links lead to the step that explains the omission", () => {
  const missing = {jobId: "a", reason: "report_missing", staleReasons: []} as const;
  assert.equal(rankingRecoveryAnchor({...missing, staleReasons: [], recoveryCode: "description_incomplete"}), "job-description");
  assert.equal(rankingRecoveryAnchor({...missing, staleReasons: [], recoveryCode: "requirement_analysis_failed"}), "job-requirements");
  assert.equal(rankingRecoveryAnchor({jobId: "a", reason: "hard_conflict", staleReasons: []}), "job-match");
  assert.equal(rankingRecoveryAnchor({jobId: "a", reason: "report_stale", staleReasons: ["job_description_changed"]}), "job-match");
});

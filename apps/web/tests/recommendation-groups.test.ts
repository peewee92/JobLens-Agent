import assert from "node:assert/strict";
import test from "node:test";
import {groupRecommendationItems, selectDefaultTargetSuggestions, recommendationGroups} from "../lib/match-report";
import type {MatchRecommendation} from "../lib/contracts";

function items(...recommendations: MatchRecommendation[]) {
  return recommendations.map((recommendation, i) => ({report: {reportId: `report_${i}`, recommendation}}));
}

test("every report appears once in its evidence-based group; input order is retained", () => {
  const input = items("strong", "good", "stretch", "low", "blocked");
  const grouped = groupRecommendationItems(input);
  assert.deepEqual(grouped.priority, input.slice(0, 2));
  assert.deepEqual(grouped.challenge, [input[2]]);
  assert.deepEqual(grouped.insufficient, [input[3]]);
  assert.deepEqual(grouped.blocked, [input[4]]);
  assert.equal(Object.values(grouped).flat().length, input.length);
  assert.deepEqual(input.map(x => x.report.recommendation), ["strong", "good", "stretch", "low", "blocked"]);
});

test("fewer than three supported suggestions stay fewer, never padded with unknown or conflict", () => {
  assert.deepEqual(selectDefaultTargetSuggestions(items("low", "blocked")), []);
  const input = items("good", "low", "blocked");
  assert.deepEqual(selectDefaultTargetSuggestions(input), [input[0]]);
  const mixed = items("strong", "good", "stretch", "stretch", "low");
  assert.deepEqual(selectDefaultTargetSuggestions(mixed), mixed.slice(0, 3));
});

test("challenge-only suggestions remain explicitly challenge, not promoted to priority", () => {
  const input = items("stretch", "low");
  const groups = groupRecommendationItems(input);
  assert.equal(groups.priority.length, 0);
  assert.deepEqual(selectDefaultTargetSuggestions(input), groups.challenge);
  assert.match(recommendationGroups.challenge.label, /挑战／待核实/);
  assert.match(recommendationGroups.challenge.description, /不代表所有条件已经满足/);
});

import {targetSelectionBlockMessage} from "../lib/career-agent-run";

test("insufficient evidence and missing reports have different actionable messages after reload", () => {
  assert.match(targetSelectionBlockMessage("target_evidence_insufficient")!, /证据不足.*无法提出可靠目标/);
  assert.match(targetSelectionBlockMessage("target_evidence_insufficient")!, /核实资料或查看岗位要求/);
  assert.match(targetSelectionBlockMessage("match_not_ready")!, /必要时生成或更新匹配结果/);
  assert.equal(targetSelectionBlockMessage("completed"), null);
});

import {userFacingErrorCode} from "../lib/user-facing-errors";

test("runtime persistence failures point to repair or re-read without deleting history or restarting", () => {
  assert.match(userFacingErrorCode("career_agent_storage_not_ready", "failed"), /副本验证数据库升级/);
  assert.match(userFacingErrorCode("career_agent_state_conflict", "failed"), /重新读取运行状态/);
});

test("save failure does not claim another request updated the run", () => {
  const message = userFacingErrorCode("career_agent_save_failed", "failed");
  assert.match(message, /回滚/);
  assert.match(message, /继续分析/);
  assert.doesNotMatch(message, /其他请求更新/);
});

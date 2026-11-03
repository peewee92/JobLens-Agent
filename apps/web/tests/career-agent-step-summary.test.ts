import test from "node:test";
import assert from "node:assert/strict";
import {careerAgentStepSummary} from "../lib/career-agent-run";

test("recovery explains an accepted decision without falsely claiming completion", () => {
  const message = careerAgentStepSummary("skill_gap_ready");
  assert.match(message, /已确认/);
  assert.match(message, /尚未保存/);
  assert.match(message, /不必重复确认/);
  assert.doesNotMatch(message, /skill_gap_ready|已完成/);
});
test("known steps explain their state without inventing success", () => {
  assert.match(careerAgentStepSummary("analysis_created"), /尚需继续/);
  assert.match(careerAgentStepSummary("rank_jobs"), /排序已保存/);
  assert.match(careerAgentStepSummary("continue_stale_career_context"), /已变化/);
  assert.match(careerAgentStepSummary("match_not_ready"), /缺少/);
});
test("unknown step has a conservative fallback and does not echo arbitrary input", () => {
  for (const step of ["unknown-private-detail", "__proto__", "toString"]) {
    const result = careerAgentStepSummary(step);
    assert.match(result, /查看当前运行状态/);
    assert.doesNotMatch(result, /unknown-private-detail|__proto__|toString|已完成/);
  }
});

test("stale approval explains that job or matching inputs may have changed", () => {
  const message = careerAgentStepSummary("resume_stale_match_reports");
  assert.match(message, /岗位或匹配依据已变化/);
  assert.match(message, /重新分析/);
  assert.doesNotMatch(message, /已完成/);
});

import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import {renderToStaticMarkup} from "react-dom/server";
import {BatchMatchSuccesses} from "../components/batch-match-successes";

const render = (jobIds: string[]) => renderToStaticMarkup(React.createElement(BatchMatchSuccesses, {jobIds}));
test("partial success is accessible without including failed jobs", () => {
  const html = render(["job_a", "job_b"]);
  assert.match(html, /本次已完成的岗位（2）/);
  assert.match(html, /尚未完成的岗位不代表不适合/);
  assert.match(html, /scopeJobId=job_a&amp;scopeJobId=job_b/);
  assert.match(html, /href="\/jobs\/job_a"/);
  assert.doesNotMatch(html, /job_failed/);
  assert.equal(render([]), "");
});
test("the selection link preserves the whole 50-job range", () => {
  const html = render(Array.from({length: 50}, (_, i) => `job_${i}`));
  assert.match(html, /本次已完成的岗位（50）/);
  assert.equal((html.match(/scopeJobId=/g) ?? []).length, 50);
  assert.match(html, /scopeJobId=job_49/);
});

test("more than 50 successful jobs are presented as separate complete scopes", () => {
  const html = render(Array.from({length: 51}, (_, i) => `job_${i}`));
  assert.match(html, /分析已完成岗位第 1 组（50 个）/);
  assert.match(html, /分析已完成岗位第 2 组（1 个）/);
  assert.match(html, /scopeJobId=job_50/);
  assert.equal((html.match(/scopeJobId=/g) ?? []).length, 51);
});

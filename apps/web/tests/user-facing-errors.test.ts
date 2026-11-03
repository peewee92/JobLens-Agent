import assert from "node:assert/strict";
import test from "node:test";

import {userFacingApiError} from "@/lib/user-facing-errors";

test("primary user flows translate stable backend errors into actionable Chinese", () => {
  assert.equal(
    userFacingApiError(
      {error: {code: "context_version_conflict", message: "stale version 4"}},
      "保存失败，请稍后重试。",
    ),
    "这份信息刚刚发生了更新。请刷新页面，确认最新内容后再保存。",
  );
  assert.equal(
    userFacingApiError(
      {error: {code: "resume_document_too_large", message: "max bytes exceeded"}},
      "简历整理失败，请稍后重试。",
    ),
    "简历文件超过 5 MiB，请压缩文件或换一份更小的文件。",
  );
  assert.equal(
    userFacingApiError(
      {error: {code: "requirement_extractor_failed", message: "OpenAI HTTPStatusError"}},
      "岗位要求分析失败，请稍后重试。",
    ),
    "这次岗位要求分析没有成功，请稍后重试。",
  );
  assert.equal(
    userFacingApiError(
      {error: {code: "semantic_matcher_unavailable", message: "provider disabled"}},
      "完整匹配建议生成失败，请稍后重试。",
    ),
    "完整匹配建议暂时不可用；你仍可以先参考上方的硬条件判断。",
  );
  assert.equal(
    userFacingApiError(
      {error: {code: "feedback_match_report_stale", message: "stale report"}},
      "反馈暂时保存失败，请稍后再试。",
    ),
    "这个岗位的推荐刚刚更新了，请根据最新建议重新判断。",
  );
});

test("unknown backend messages are not leaked into the ordinary user flow", () => {
  assert.equal(
    userFacingApiError(
      {error: {code: "unexpected_internal_detail", message: "SQLAlchemy session rollback failed"}},
      "操作没有完成，请稍后重试。",
    ),
    "操作没有完成，请稍后重试。",
  );
});

test("connection outage retains the original command and suggests checking status first", () => {
  const message = userFacingApiError({error: {code: "backend_unavailable", message: "private socket details"}}, "failed");
  assert.match(message, /原请求已保留/);
  assert.match(message, /查看请求状态/);
  assert.doesNotMatch(message, /private socket/);
});


test("availability errors explain how to recover without exposing provider details", () => {
  assert.match(userFacingApiError({error: {code: "job_user_marked_inactive", message: "private"}}, "失败"), /恢复标记/);
  const changed = userFacingApiError({error: {code: "job_availability_changed", message: "private"}}, "失败");
  assert.match(changed, /结果未保存/);
  assert.match(changed, /如已发出模型请求/);
  assert.doesNotMatch(changed, /private/);
});

test("description changed during extraction is actionable and does not promise cancellation", () => {
  const message = userFacingApiError({error: {code: "job_description_changed_during_extraction", message: "private"}}, "失败");
  assert.match(message, /岗位描述发生变化/);
  assert.match(message, /结果未保存/);
  assert.match(message, /如已发出模型请求/);
  assert.doesNotMatch(message, /private/);
});

test("superseded extraction directs the user to the saved result", () => {
  const message = userFacingApiError({error: {code: "requirement_extraction_superseded", message: "private"}}, "失败");
  assert.match(message, /查看已有结果/);
  assert.match(message, /本次结果未保存/);
  assert.match(message, /如已发出模型请求/);
  assert.doesNotMatch(message, /private/);
});

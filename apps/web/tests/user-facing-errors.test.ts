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

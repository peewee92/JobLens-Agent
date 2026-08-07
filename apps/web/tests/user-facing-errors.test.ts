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

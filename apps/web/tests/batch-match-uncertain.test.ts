import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import {renderToStaticMarkup} from "react-dom/server";
import {BatchMatchUncertainNotice} from "../components/batch-match-uncertain-notice";
import {isUncertainMatchResponse} from "../lib/import-match-batching";

test("timeouts and server errors do not establish rollback", () => {
  for (const status of [408, 500, 502, 503, 504]) assert.equal(isUncertainMatchResponse(status), true);
  for (const status of [200, 400, 409, 422]) assert.equal(isUncertainMatchResponse(status), false);
});

test("uncertain outcome tells user to verify persisted results before retry", () => {
  const html = renderToStaticMarkup(React.createElement(BatchMatchUncertainNotice));
  assert.match(html, /可能已保存部分匹配结果/);
  assert.match(html, /不要直接重复提交/);
  assert.match(html, /刷新并核对结果/);
});

test("requirement extraction has its own uncertain-result wording", () => {
  const html = renderToStaticMarkup(React.createElement(BatchMatchUncertainNotice, {kind: "requirements"}));
  assert.match(html, /岗位要求分析结果/);
  assert.match(html, /刷新并核对结果/);
  assert.doesNotMatch(html, /部分匹配结果/);
});
